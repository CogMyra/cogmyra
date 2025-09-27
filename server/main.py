# server/main.py
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterable, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from openai import APIStatusError, BadRequestError, OpenAI, OpenAIError, RateLimitError
from pydantic import BaseModel, Field

# -------------------------------------------------------------------
# Version (bump this so we can confirm deploy)
# -------------------------------------------------------------------
VERSION = "api-v5.7.4-gpt5-tempfix2"

# -------------------------------------------------------------------
# Env / Config
# -------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SERVER_API_KEY = os.getenv("SERVER_API_KEY", "")

# CORS allowlist from env (comma-separated), plus localhost
CORS_ENV = os.getenv("CORS_ORIGINS", "").strip()
CORS_ALLOWLIST = [o.strip() for o in CORS_ENV.split(",") if o.strip()]
LOCAL_HOSTS = ["http://localhost", "http://127.0.0.1"]

# -------------------------------------------------------------------
# App
# -------------------------------------------------------------------
app = FastAPI(title="CogMyra API", version=VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWLIST + LOCAL_HOSTS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------------
# Auth
# -------------------------------------------------------------------
def require_server_key(request: Request) -> None:
    if not SERVER_API_KEY:
        return  # open for local/dev if not set
    key = request.headers.get("X-API-Key", "")
    if key != SERVER_API_KEY:
        raise HTTPException(
            status_code=401, detail="Unauthorized: missing or invalid API key"
        )


# -------------------------------------------------------------------
# Logging middleware
# -------------------------------------------------------------------
@app.middleware("http")
async def access_log(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
        return response
    finally:
        dur_ms = int((time.perf_counter() - start) * 1000)
        origin = request.headers.get("Origin", "")
        model = ""
        try:
            if request.url.path.endswith("/api/chat"):
                body = await request.body()
                if body:
                    payload = json.loads(body.decode("utf-8"))
                    model = payload.get("model", "")
        except Exception:
            pass
        print(
            json.dumps(
                {
                    "path": request.url.path,
                    "method": request.method,
                    "origin": origin,
                    "model": model,
                    "latency_ms": dur_ms,
                }
            )
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
    temperature: Optional[float] = None  # optional


class ChatResponse(BaseModel):
    reply: str
    version: str
    latency_ms: int
    usage: Dict[str, Any] = {}
    request_id: Optional[str] = Field(default=None, alias="request_id")


class ErrorEnvelope(BaseModel):
    error: Dict[str, Any]
    request_id: Optional[str] = None


# -------------------------------------------------------------------
# Sessions (in-memory)
# -------------------------------------------------------------------
MAX_HISTORY = 12
_sessions: Dict[str, List[Dict[str, str]]] = {}


def _session_get(session_id: str) -> List[Dict[str, str]]:
    return _sessions.setdefault(session_id, [])


def _session_add(session_id: str, msgs: List[Dict[str, str]]) -> None:
    hist = _session_get(session_id)
    hist.extend(msgs)
    if len(hist) > MAX_HISTORY:
        _sessions[session_id] = hist[-MAX_HISTORY:]


def _session_reset(session_id: str) -> None:
    _sessions[session_id] = []


# -------------------------------------------------------------------
# OpenAI
# -------------------------------------------------------------------
def _client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server missing OPENAI_API_KEY")
    return OpenAI(api_key=OPENAI_API_KEY)


def _normalize_usage(u: Any) -> Dict[str, Any]:
    if not u:
        return {}
    if hasattr(u, "model_dump"):
        return dict(u.model_dump())
    if isinstance(u, dict):
        return dict(u)
    out: Dict[str, Any] = {}
    for k in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt_tokens_details",
        "completion_tokens_details",
    ):
        v = getattr(u, k, None)
        if v is not None:
            out[k] = v
    return out


def _provider_error_to_envelope(e: Exception) -> ErrorEnvelope:
    code = "UPSTREAM_ERROR"
    msg = f"OpenAI error: {str(e)}"
    req_id = None
    if isinstance(e, RateLimitError):
        code = "RATE_LIMITED"
    elif isinstance(e, BadRequestError):
        code = "BAD_REQUEST"
    elif isinstance(e, APIStatusError):
        if e.status_code == 401:
            code = "AUTH_ERROR"
        elif e.status_code == 429:
            code = "RATE_LIMITED"
        elif 500 <= e.status_code < 600:
            code = "UPSTREAM_5XX"
        req_id = getattr(e, "request_id", None)
    return ErrorEnvelope(error={"code": code, "message": msg}, request_id=req_id)


# -------------------------------------------------------------------
# Health
# -------------------------------------------------------------------
@app.get("/api/health", response_class=JSONResponse)
def health():
    return {"ok": "true", "version": VERSION}


@app.get("/api/health/full", response_class=JSONResponse)
def health_full():
    upstream = {"openai": "ok", "error": None}
    try:
        if not OPENAI_API_KEY:
            upstream = {"openai": "missing_api_key", "error": None}
    except Exception as e:
        upstream = {"openai": "error", "error": str(e)}
    return {
        "ok": True,
        "version": VERSION,
        "env": {
            "OPENAI_API_KEY": bool(OPENAI_API_KEY),
            "SERVER_API_KEY": bool(SERVER_API_KEY),
        },
        "upstream": upstream,
    }


# -------------------------------------------------------------------
# Chat (non-stream)
# -------------------------------------------------------------------
@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, _: None = Depends(require_server_key)):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server missing OPENAI_API_KEY")
    start = time.perf_counter()
    try:
        oai = _client()

        history = _session_get(req.sessionId)
        new_msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        send_msgs = history + new_msgs

        # ---- IMPORTANT: never send temperature for gpt-5* models
        kwargs: Dict[str, Any] = {"model": req.model, "messages": send_msgs}
        if not req.model.lower().startswith("gpt-5") and req.temperature is not None:
            kwargs["temperature"] = req.temperature

        resp = oai.chat.completions.create(**kwargs)

        reply = resp.choices[0].message.content if resp.choices else ""
        latency_ms = int((time.perf_counter() - start) * 1000)
        usage = _normalize_usage(getattr(resp, "usage", None))
        request_id = getattr(resp, "id", None)

        _session_add(
            req.sessionId, new_msgs + [{"role": "assistant", "content": reply}]
        )

        return ChatResponse(
            reply=reply,
            version=VERSION,
            latency_ms=latency_ms,
            usage=usage,
            request_id=request_id,
        )
    except OpenAIError as e:
        env = _provider_error_to_envelope(e)
        return JSONResponse(
            status_code=502, content=json.loads(env.model_dump_json(by_alias=True))
        )
    except Exception as e:
        env = ErrorEnvelope(
            error={"code": "SERVER_ERROR", "message": str(e)}, request_id=None
        )
        return JSONResponse(
            status_code=500, content=json.loads(env.model_dump_json(by_alias=True))
        )


# -------------------------------------------------------------------
# Chat (SSE stream)
# -------------------------------------------------------------------
def _sse_line(obj: dict | str, *, event: Optional[str] = None) -> bytes:
    data = json.dumps(obj) if isinstance(obj, dict) else str(obj)
    if event:
        return (f"event: {event}\n" f"data: {data}\n\n").encode("utf-8")
    return (f"data: {data}\n\n").encode("utf-8")


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, _: None = Depends(require_server_key)):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server missing OPENAI_API_KEY")

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
            request_id = getattr(stream, "id", None)
            for ev in stream:
                delta = (
                    getattr(ev.choices[0].delta, "content", "") if ev.choices else ""
                )
                if delta:
                    parts.append(delta)
                    yield _sse_line({"delta": delta})
            reply = "".join(parts)
            latency_ms = int((time.perf_counter() - start) * 1000)
            usage = _normalize_usage(getattr(stream, "usage", None))
            _session_add(
                req.sessionId, new_msgs + [{"role": "assistant", "content": reply}]
            )
            yield _sse_line(
                {
                    "final": True,
                    "reply": reply,
                    "latency_ms": latency_ms,
                    "usage": usage,
                    "version": VERSION,
                    "request_id": request_id,
                },
                event="done",
            )
        except OpenAIError as e:
            env = _provider_error_to_envelope(e)
            yield _sse_line(
                json.loads(env.model_dump_json(by_alias=True)), event="error"
            )
        except Exception as e:
            env = ErrorEnvelope(
                error={"code": "SERVER_ERROR", "message": str(e)}, request_id=None
            )
            yield _sse_line(
                json.loads(env.model_dump_json(by_alias=True)), event="error"
            )

    return StreamingResponse(gen(), media_type="text/event-stream")


# -------------------------------------------------------------------
# Session reset
# -------------------------------------------------------------------
class SessionResetRequest(BaseModel):
    sessionId: str = Field(..., alias="sessionId")


@app.post("/api/session/reset")
def session_reset(req: SessionResetRequest, _: None = Depends(require_server_key)):
    _session_reset(req.sessionId)
    return {"ok": True, "sessionId": req.sessionId, "version": VERSION}
