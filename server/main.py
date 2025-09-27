# server/main.py
from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from openai import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    NotFoundError,
    OpenAI,
    RateLimitError,
)
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------
VERSION = "api-v5.5-sessions"

# ---------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
SERVER_API_KEY = os.getenv("SERVER_API_KEY", "")
CORS_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()
]
MAX_SESSION_MESSAGES = int(
    os.getenv("MAX_SESSION_MESSAGES", "20")
)  # last N msgs kept per session

if not OPENAI_API_KEY:
    # We'll still boot to show a clear error on use
    pass

# ---------------------------------------------------------------------
# OpenAI client
# ---------------------------------------------------------------------
oai = OpenAI(api_key=OPENAI_API_KEY)

# ---------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------
app = FastAPI(title="CogMyra API", version=VERSION)

# CORS (future-proof; configure via env)
allow_origins = CORS_ORIGINS or [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------
# Auth dep (optional; only enforced if SERVER_API_KEY is set)
# ---------------------------------------------------------------------
def require_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    if SERVER_API_KEY and x_api_key != SERVER_API_KEY:
        raise HTTPException(
            status_code=401, detail="Unauthorized: missing or invalid API key"
        )


# ---------------------------------------------------------------------
# Request models / responses
# ---------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    sessionId: str = Field(..., min_length=1, max_length=200)
    model: Optional[str] = None
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.2


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_tokens_details: dict = Field(default_factory=dict)
    completion_tokens_details: dict = Field(default_factory=dict)


class ChatResponse(BaseModel):
    reply: str
    version: str
    latency_ms: int
    usage: Usage


class ErrorEnvelope(BaseModel):
    error: Dict[str, str]
    request_id: Optional[str] = None


# ---------------------------------------------------------------------
# In-memory session store
#   sessions[sessionId] => deque of ChatMessage (maxlen = MAX_SESSION_MESSAGES)
# ---------------------------------------------------------------------
sessions: Dict[str, Deque[ChatMessage]] = defaultdict(
    lambda: deque(maxlen=MAX_SESSION_MESSAGES)
)


# Utilities
def _map_usage(u) -> Usage:
    # OpenAI python SDK usage may be on top-level 'usage' object
    if not u:
        return Usage()
    # Normalize to our Usage model
    try:
        return Usage(
            prompt_tokens=getattr(u, "prompt_tokens", 0) or u.get("prompt_tokens", 0),
            completion_tokens=getattr(u, "completion_tokens", 0)
            or u.get("completion_tokens", 0),
            total_tokens=getattr(u, "total_tokens", 0) or u.get("total_tokens", 0),
            prompt_tokens_details=getattr(u, "prompt_tokens_details", {})
            or u.get("prompt_tokens_details", {})
            or {},
            completion_tokens_details=getattr(u, "completion_tokens_details", {})
            or u.get("completion_tokens_details", {})
            or {},
        )
    except Exception:
        return Usage()


def _error_envelope(
    exc: Exception, default_message: str = "Provider error"
) -> Tuple[ErrorEnvelope, int]:
    code = "PROVIDER_ERROR"
    message = default_message
    status = 500
    request_id = None

    if isinstance(exc, NotFoundError):
        code = "MODEL_NOT_FOUND"
        message = "The requested model was not found or you do not have access to it."
        status = 404
    elif isinstance(exc, AuthenticationError):
        code = "UNAUTHORIZED"
        message = "OpenAI rejected your API key."
        status = 401
    elif isinstance(exc, RateLimitError):
        code = "RATE_LIMIT"
        message = "Rate limit hit. Please retry after a short delay."
        status = 429
    elif isinstance(exc, APIConnectionError):
        code = "UPSTREAM_UNAVAILABLE"
        message = "Could not reach OpenAI. Try again."
        status = 502
    elif isinstance(exc, APIError):
        code = "UPSTREAM_ERROR"
        message = "OpenAI returned an error."
        status = 502

    # Try to extract a request id if present
    try:
        request_id = getattr(exc, "request_id", None) or getattr(exc, "response", None)
        if hasattr(request_id, "request_id"):
            request_id = request_id.request_id
    except Exception:
        request_id = None

    return ErrorEnvelope(
        error={"code": code, "message": message}, request_id=request_id
    ), status


def _log_request(start: float, request: Request, model: str, status: int) -> None:
    try:
        origin = request.headers.get("origin", "")
        payload = {
            "path": request.url.path,
            "method": request.method,
            "origin": origin,
            "model": model,
            "latency_ms": int((time.perf_counter() - start) * 1000),
        }
        # Use FastAPI logger (captured by Render)
        app.logger.info(json.dumps(payload))
        # Also print for good measure
        print(json.dumps(payload))
    except Exception:
        pass


# ---------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    return {"ok": "true", "version": VERSION}


# ---------------------------------------------------------------------
# /api/chat (non-streaming) — with session memory
# ---------------------------------------------------------------------
@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request, _=Depends(require_api_key)):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server missing OPENAI_API_KEY")

    start = time.perf_counter()
    model = req.model or DEFAULT_MODEL

    # Build full history = prior session + new messages
    history = list(sessions[req.sessionId])  # copy
    # Only accept simple roles expected by OpenAI
    new_msgs = [
        {"role": m.role, "content": m.content}
        for m in req.messages
        if m.role in ("system", "user", "assistant")
    ]
    prior_msgs = [
        {"role": m.role, "content": m.content}
        for m in history
        if m.role in ("system", "user", "assistant")
    ]
    messages = prior_msgs + new_msgs

    try:
        resp = oai.chat.completions.create(
            model=model,
            messages=messages,
            temperature=req.temperature or 0.2,
        )
        reply = resp.choices[0].message.content or ""
        latency_ms = int((time.perf_counter() - start) * 1000)
        usage = _map_usage(getattr(resp, "usage", None) or {})

        # Persist: add user messages then assistant reply
        for m in req.messages:
            sessions[req.sessionId].append(m)
        sessions[req.sessionId].append(ChatMessage(role="assistant", content=reply))

        _log_request(start, request, model, 200)

        return ChatResponse(
            reply=reply, version=VERSION, latency_ms=latency_ms, usage=usage
        )

    except Exception as e:
        env, status = _error_envelope(e)
        _log_request(start, request, model, status)
        return JSONResponse(
            status_code=status, content=json.loads(env.model_dump_json())
        )


# ---------------------------------------------------------------------
# SSE streaming endpoint — with session memory
# ---------------------------------------------------------------------
def _sse_line(obj: dict | str, *, event: str | None = None) -> bytes:
    if event:
        return (f"event: {event}\n" + f"data: {json.dumps(obj)}\n\n").encode("utf-8")
    return (f"data: {json.dumps(obj)}\n\n").encode("utf-8")


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, request: Request, _=Depends(require_api_key)):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server missing OPENAI_API_KEY")

    start = time.perf_counter()
    model = req.model or DEFAULT_MODEL

    # Build full history = prior session + new messages
    history = list(sessions[req.sessionId])
    new_msgs = [
        {"role": m.role, "content": m.content}
        for m in req.messages
        if m.role in ("system", "user", "assistant")
    ]
    prior_msgs = [
        {"role": m.role, "content": m.content}
        for m in history
        if m.role in ("system", "user", "assistant")
    ]
    messages = prior_msgs + new_msgs

    def gen():
        try:
            stream = oai.chat.completions.create(
                model=model,
                messages=messages,
                temperature=req.temperature or 0.2,
                stream=True,
            )
            full_text: List[str] = []
            for event in stream:
                piece = event.choices[0].delta.content or ""
                if piece:
                    full_text.append(piece)
                    yield _sse_line({"delta": piece})

            reply = "".join(full_text)
            latency_ms = int((time.perf_counter() - start) * 1000)
            usage = _map_usage(getattr(stream, "usage", None) or {})

            # Persist session: user msgs then assistant reply
            for m in req.messages:
                sessions[req.sessionId].append(m)
            sessions[req.sessionId].append(ChatMessage(role="assistant", content=reply))

            _log_request(start, request, model, 200)
            yield _sse_line(
                {
                    "final": True,
                    "reply": reply,
                    "latency_ms": latency_ms,
                    "usage": json.loads(usage.model_dump_json()),
                    "version": VERSION,
                },
                event="done",
            )
        except Exception as e:
            env, status = _error_envelope(e)
            _log_request(start, request, model, status)
            yield _sse_line(json.loads(env.model_dump_json()), event="error")

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------------------------------------------------------------------
# Session utils
# ---------------------------------------------------------------------
class ResetRequest(BaseModel):
    sessionId: str = Field(..., min_length=1, max_length=200)


@app.post("/api/session/reset")
def session_reset(req: ResetRequest, _=Depends(require_api_key)):
    sessions.pop(req.sessionId, None)
    return {"ok": True, "sessionId": req.sessionId, "version": VERSION}
