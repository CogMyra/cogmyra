# server/main.py
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from openai import OpenAI, OpenAIError, BadRequestError, RateLimitError, APIStatusError
from pydantic import BaseModel, Field

# -------------------------------------------------------------------
# Version tag (used by /api/health)
# -------------------------------------------------------------------
VERSION = "api-v5.7.4-gpt5-tempfix2"

# -------------------------------------------------------------------
# Env / Config
# -------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SERVER_API_KEY = os.getenv("SERVER_API_KEY", "")

# Optional, comma-separated origins in env (takes precedence if present)
CORS_ORIGINS_ENV = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()
]

DEFAULT_CORS = [
    "https://cogmyra.github.io",  # GitHub Pages origin
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

ALLOWED_ORIGINS = CORS_ORIGINS_ENV or DEFAULT_CORS

# -------------------------------------------------------------------
# App & CORS
# -------------------------------------------------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,  # header API key only; no cookies
    allow_methods=["*"],
    allow_headers=["*"],  # include x-api-key
    max_age=600,
)


# -------------------------------------------------------------------
# Models
# -------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    sessionId: str = Field(..., alias="sessionId")
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = None


# We intentionally DO NOT Pydantic-validate the OpenAI "usage" object, since
# different models (reasoners etc.) return nested dicts. We'll pass it through.


# -------------------------------------------------------------------
# Simple API key dependency
# -------------------------------------------------------------------
def require_server_key(req: Request) -> None:
    key = req.headers.get("X-API-Key") or req.headers.get("x-api-key")
    if not key or key != SERVER_API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")


# -------------------------------------------------------------------
# OpenAI client
# -------------------------------------------------------------------
def _client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server missing OPENAI_API_KEY")
    return OpenAI(api_key=OPENAI_API_KEY)


# -------------------------------------------------------------------
# Tiny in-memory session store (last N messages per session)
# -------------------------------------------------------------------
_SESSION: Dict[str, List[Dict[str, str]]] = {}
_SESSION_LIMIT = 20


def _session_get(session_id: str) -> List[Dict[str, str]]:
    return _SESSION.get(session_id, [])


def _session_add(session_id: str, new_messages: List[Dict[str, str]]) -> None:
    history = _SESSION.get(session_id, [])
    history = (history + new_messages)[-(_SESSION_LIMIT):]
    _SESSION[session_id] = history


# -------------------------------------------------------------------
# Error envelope helpers
# -------------------------------------------------------------------
def _error_envelope(
    code: str, message: str, request_id: Optional[str] = None
) -> Dict[str, Any]:
    return {"error": {"code": code, "message": message}, "request_id": request_id}


def _provider_error_to_envelope(e: OpenAIError) -> Tuple[int, Dict[str, Any]]:
    req_id = getattr(e, "request_id", None)
    # Map common upstream types to clear client-facing messages
    if isinstance(e, BadRequestError):
        return 400, _error_envelope(
            "UPSTREAM_BAD_REQUEST", f"OpenAI error: {e.message}", req_id
        )
    if isinstance(e, RateLimitError):
        return 429, _error_envelope(
            "UPSTREAM_RATE_LIMIT", "OpenAI rate limit hit.", req_id
        )
    if isinstance(e, APIStatusError) and 500 <= e.status_code < 600:
        return 502, _error_envelope("UPSTREAM_5XX", f"OpenAI {e.status_code}", req_id)
    return 502, _error_envelope("UPSTREAM_ERROR", f"OpenAI error: {str(e)}", req_id)


# -------------------------------------------------------------------
# Health
# -------------------------------------------------------------------
@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"ok": "true", "version": VERSION}


@app.get("/api/health/full")
def health_full(_: None = Depends(require_server_key)) -> JSONResponse:
    # Env presence only (no secrets)
    env = {
        "OPENAI_API_KEY": bool(OPENAI_API_KEY),
        "SERVER_API_KEY": bool(SERVER_API_KEY),
    }
    # Try a trivial upstream ping
    upstream_status = {"openai": "ok", "error": None}
    try:
        _ = _client()  # will throw if missing key
    except Exception as e:
        upstream_status["openai"] = "error"
        upstream_status["error"] = str(e)
    return JSONResponse(
        content={
            "ok": True,
            "version": VERSION,
            "env": env,
            "upstream": upstream_status,
        }
    )


# -------------------------------------------------------------------
# Sessions: reset
# -------------------------------------------------------------------
@app.post("/api/session/reset")
def session_reset(
    body: Dict[str, str], _: None = Depends(require_server_key)
) -> Dict[str, Any]:
    sid = body.get("sessionId")
    if not sid:
        raise HTTPException(status_code=400, detail="Missing sessionId")
    _SESSION.pop(sid, None)
    return {"ok": True, "sessionId": sid, "version": VERSION}


# -------------------------------------------------------------------
# Chat (non-streaming)
# -------------------------------------------------------------------
@app.post("/api/chat")
def chat(req: ChatRequest, _: None = Depends(require_server_key)) -> JSONResponse:
    oai = _client()
    history = _session_get(req.sessionId)

    new_msgs = [{"role": m.role, "content": m.content} for m in req.messages]
    send_msgs = history + new_msgs

    kwargs: Dict[str, Any] = {"model": req.model, "messages": send_msgs}
    # gpt-5 currently requires default temperature; omit if provided
    if not req.model.lower().startswith("gpt-5") and req.temperature is not None:
        kwargs["temperature"] = req.temperature

    start = time.perf_counter()
    try:
        resp = oai.chat.completions.create(**kwargs)
        latency_ms = int((time.perf_counter() - start) * 1000)

        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        # OpenAI SDK usage is a pydantic object; convert to plain dict if present
        usage_dict = json.loads(usage.model_dump_json()) if usage is not None else {}

        # persist new turn
        _session_add(req.sessionId, new_msgs)

        out = {
            "reply": text,
            "version": VERSION,
            "latency_ms": latency_ms,
            "usage": usage_dict,
            "request_id": getattr(resp, "id", None),
        }
        return JSONResponse(content=out)
    except OpenAIError as e:
        status, env = _provider_error_to_envelope(e)
        return JSONResponse(status_code=status, content=env)
    except Exception as e:
        return JSONResponse(
            status_code=500, content=_error_envelope("SERVER_ERROR", str(e))
        )


# -------------------------------------------------------------------
# Chat (SSE streaming)
# -------------------------------------------------------------------
def _sse_line(obj: Dict[str, Any] | str, *, event: Optional[str] = None) -> bytes:
    data = json.dumps(obj) if isinstance(obj, dict) else str(obj)
    if event:
        return (f"event: {event}\n" f"data: {data}\n\n").encode("utf-8")
    return (f"data: {data}\n\n").encode("utf-8")


@app.post("/api/chat/stream")
def chat_stream(
    req: ChatRequest, _: None = Depends(require_server_key)
) -> StreamingResponse:
    oai = _client()
    history = _session_get(req.sessionId)

    new_msgs = [{"role": m.role, "content": m.content} for m in req.messages]
    send_msgs = history + new_msgs

    kwargs: Dict[str, Any] = {"model": req.model, "messages": send_msgs, "stream": True}
    if not req.model.lower().startswith("gpt-5") and req.temperature is not None:
        kwargs["temperature"] = req.temperature

    start = time.perf_counter()

    def gen() -> Iterable[bytes]:
        try:
            stream = oai.chat.completions.create(**kwargs)
            parts: List[str] = []
            usage_obj: Dict[str, Any] = {}
            req_id: Optional[str] = None

            for chunk in stream:
                # request id is available on each chunk; first one is fine
                req_id = req_id or getattr(chunk, "id", None)
                delta = ""
                try:
                    delta = chunk.choices[0].delta.content or ""
                except Exception:
                    delta = ""

                if delta:
                    parts.append(delta)
                    yield _sse_line({"delta": delta})

            # usage is available on the terminal chunk in new SDKs; best-effort
            try:
                if hasattr(stream, "usage") and stream.usage is not None:
                    usage_obj = json.loads(stream.usage.model_dump_json())
            except Exception:
                usage_obj = {}

            final_text = "".join(parts)
            latency_ms = int((time.perf_counter() - start) * 1000)

            # persist
            _session_add(req.sessionId, new_msgs)

            yield _sse_line(
                {
                    "final": True,
                    "reply": final_text,
                    "latency_ms": latency_ms,
                    "usage": usage_obj,
                    "version": VERSION,
                    "request_id": req_id,
                },
                event="done",
            )
        except OpenAIError as e:
            status, env = _provider_error_to_envelope(e)
            yield _sse_line(env, event="error")
        except Exception as e:
            yield _sse_line(_error_envelope("SERVER_ERROR", str(e)), event="error")

    return StreamingResponse(gen(), media_type="text/event-stream")
