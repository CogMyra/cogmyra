# server/main.py
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterable, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# OpenAI SDK (>=1.x)
from openai import APIError, AuthenticationError, NotFoundError, OpenAI, RateLimitError

# --------------------------------------------------------------------------------------
# Version
# --------------------------------------------------------------------------------------
VERSION = "api-v5.4-cors"

# --------------------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------------------
app = FastAPI(title="CogMyra API", version=VERSION)


# --------------------------------------------------------------------------------------
# CORS (future-proof)
# - Allow prod origin(s) from env: CORS_ORIGINS="https://yourapp.com,https://app.example"
# - Also allow any localhost port via a regex, no credentials.
# --------------------------------------------------------------------------------------
def _parse_env_origins(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [o.strip() for o in value.split(",") if o.strip()]


PROD_ORIGINS = _parse_env_origins(os.getenv("CORS_ORIGINS"))
# Regex allows: http://localhost:*, http://127.0.0.1:*, http://0.0.0.0:*
LOCALHOST_REGEX = r"^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=PROD_ORIGINS,  # explicit prod origins from env
    allow_origin_regex=LOCALHOST_REGEX,  # any localhost port
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,  # simpler; no cookies
)

# --------------------------------------------------------------------------------------
# OpenAI client
# --------------------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
oai = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# --------------------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def _error(code: str, message: str) -> Dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _usage_dict(usage: Any) -> Dict[str, Any]:
    if not usage:
        return {}
    # openai v1 usage has fields: prompt_tokens, completion_tokens, total_tokens
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", None) or 0,
        "total_tokens": getattr(usage, "total_tokens", None) or 0,
        "prompt_tokens_details": {
            "cached_tokens": 0,
            "audio_tokens": 0,
            "reasoning_tokens": 0,
            "accepted_prediction_tokens": 0,
            "rejected_prediction_tokens": 0,
        },
        "completion_tokens_details": {
            "cached_tokens": 0,
            "audio_tokens": 0,
            "reasoning_tokens": 0,
            "accepted_prediction_tokens": 0,
            "rejected_prediction_tokens": 0,
        },
    }


def _map_exception(e: Exception) -> JSONResponse:
    req_id = getattr(e, "request_id", None)
    if isinstance(e, NotFoundError):
        payload = _error(
            "MODEL_NOT_FOUND",
            "The requested model was not found or you do not have access to it.",
        )
    elif isinstance(e, AuthenticationError):
        payload = _error(
            "UNAUTHORIZED", "Invalid or missing API key for the upstream provider."
        )
    elif isinstance(e, RateLimitError):
        payload = _error(
            "RATE_LIMITED", "Rate limit hit. Please retry after a short delay."
        )
    elif isinstance(e, APIError):
        payload = _error(
            "UPSTREAM_ERROR",
            str(getattr(e, "message", str(e)) or "Upstream provider error."),
        )
    else:
        payload = _error("UNKNOWN", "Unexpected error. Please try again.")
    payload["request_id"] = req_id
    return JSONResponse(status_code=400, content=payload)


def _log_request(request: Request, *, model: str, started: float) -> None:
    try:
        origin = request.headers.get("origin", "")
        latency_ms = int((time.perf_counter() - started) * 1000)
        app.logger.info(
            json.dumps(
                {
                    "path": request.url.path,
                    "method": request.method,
                    "origin": origin,
                    "model": model,
                    "latency_ms": latency_ms,
                }
            )
        )
    except Exception:
        # don't fail requests if logging fails
        pass


def _sse_line(obj: Dict[str, Any] | str, *, event: Optional[str] = None) -> bytes:
    if isinstance(obj, dict):
        data = json.dumps(obj, ensure_ascii=False)
    else:
        data = obj
    if event:
        return f"event: {event}\n" f"data: {data}\n\n".encode("utf-8")
    return f"data: {data}\n\n".encode("utf-8")


# --------------------------------------------------------------------------------------
# Middleware: simple latency logger (stdout -> Render logs)
# --------------------------------------------------------------------------------------
@app.middleware("http")
async def access_log(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    _log_request(request, model="", started=started)
    return response


# --------------------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------------------
@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"ok": "true", "version": VERSION}


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server missing OPENAI_API_KEY")
    started = time.perf_counter()
    try:
        messages = [{"role": m.role, "content": m.content} for m in req.messages]
        resp = oai.chat.completions.create(
            model=req.model,
            messages=messages,
            temperature=req.temperature,
        )
        reply = (resp.choices[0].message.content or "").strip()
        usage = _usage_dict(getattr(resp, "usage", None))
        latency_ms = int((time.perf_counter() - started) * 1000)
        _log_request(request, model=req.model, started=started)
        return JSONResponse(
            content={
                "reply": reply,
                "version": VERSION,
                "latency_ms": latency_ms,
                "usage": usage,
                "request_id": getattr(resp, "id", None),
            }
        )
    except Exception as e:  # map to standard envelope
        return _map_exception(e)


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, request: Request):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server missing OPENAI_API_KEY")

    started = time.perf_counter()

    def gen() -> Iterable[bytes]:
        try:
            messages = [{"role": m.role, "content": m.content} for m in req.messages]
            stream = oai.chat.completions.create(
                model=req.model,
                messages=messages,
                temperature=req.temperature,
                stream=True,
            )
            parts: List[str] = []
            for event in stream:
                piece = getattr(event.choices[0].delta, "content", None) or ""
                if piece:
                    parts.append(piece)
                    yield _sse_line({"delta": piece})
            # done
            reply = "".join(parts).strip()
            latency_ms = int((time.perf_counter() - started) * 1000)
            usage = _usage_dict(getattr(stream, "usage", None))
            done_payload = {
                "final": True,
                "reply": reply,
                "latency_ms": latency_ms,
                "usage": usage,
                "version": VERSION,
            }
            yield _sse_line(done_payload, event="done")
            _log_request(request, model=req.model, started=started)
        except Exception as e:
            # terminal error event so client can close cleanly
            # shape: {"error":{code,message}, "request_id":...}
            resp = _map_exception(e)
            yield _sse_line(resp.body.decode("utf-8"), event="error")

    return StreamingResponse(gen(), media_type="text/event-stream")
