# server/main.py
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Literal, Optional, Sequence

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI  # type: ignore
from pydantic import BaseModel, Field

# --------------------------------------------------------------------------------------
# Config / App
# --------------------------------------------------------------------------------------

VERSION = "api-v5-stream"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    # We won't crash startup; we'll throw an informative error on request.
    pass

app = FastAPI(title="CogMyra API", version=VERSION)

# CORS — keep your existing allowlist; add your dev ports
ALLOWED_ORIGINS = [
    "https://cogmyra-web.onrender.com",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://localhost:5176",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
    "http://127.0.0.1:5176",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single OpenAI client (safe to reuse)
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# --------------------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------------------

Role = Literal["system", "user", "assistant"]


class Message(BaseModel):
    role: Role
    content: str


class ChatRequest(BaseModel):
    sessionId: str = Field(..., description="Logical chat session id")
    model: str = Field("gpt-4o-mini", description="Provider model id")
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def _require_client() -> OpenAI:
    if client is None:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "type": "MissingAPIKey",
                    "message": "OPENAI_API_KEY is not set on the server",
                },
                "version": VERSION,
            },
        )
    return client


def _map_messages(msgs: Sequence[Message]) -> List[Dict[str, str]]:
    """Pydantic -> provider format."""
    return [{"role": m.role, "content": m.content} for m in msgs]


def _normalize_usage(usage: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Always return your normalized usage shape."""
    base = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
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
    if not usage:
        return base
    # OpenAI returns keys: prompt_tokens, completion_tokens, total_tokens (and sometimes more)
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if k in usage and isinstance(usage[k], int):
            base[k] = usage[k]
    return base


def _safe_float(
    v: Optional[float], default: float, lo: float = 0.0, hi: float = 1.0
) -> float:
    if v is None:
        return default
    try:
        v = float(v)
    except Exception:
        return default
    return max(lo, min(hi, v))


def _chat_kwargs(req: ChatRequest) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "model": req.model,
        "messages": _map_messages(req.messages),
        "temperature": _safe_float(req.temperature, 0.7, 0.0, 2.0),
    }
    if req.max_tokens is not None:
        kwargs["max_tokens"] = int(req.max_tokens)
    if req.top_p is not None:
        kwargs["top_p"] = _safe_float(req.top_p, 1.0)
    if req.frequency_penalty is not None:
        kwargs["frequency_penalty"] = float(req.frequency_penalty)
    if req.presence_penalty is not None:
        kwargs["presence_penalty"] = float(req.presence_penalty)
    return kwargs


def _sse(data: Any, event: Optional[str] = None) -> bytes:
    """Encode one SSE frame."""
    if event:
        prefix = f"event: {event}\n"
    else:
        prefix = ""
    payload = json.dumps(data, ensure_ascii=False)
    return (prefix + f"data: {payload}\n\n").encode("utf-8")


# --------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"ok": "true", "version": VERSION}


@app.post("/api/chat")
def chat(req: ChatRequest) -> Dict[str, Any]:
    """
    Non-streaming chat. Keeps your existing response shape.
    """
    c = _require_client()
    start = time.perf_counter()

    try:
        resp = c.chat.completions.create(**_chat_kwargs(req))
    except Exception as e:
        # Provider error -> friendly JSON
        raise HTTPException(
            status_code=502,
            detail={
                "error": {
                    "type": e.__class__.__name__,
                    "message": str(e),
                },
                "version": VERSION,
            },
        )

    latency_ms = int((time.perf_counter() - start) * 1000)

    text = (resp.choices[0].message.content or "").strip()
    usage = None
    if getattr(resp, "usage", None):
        # Convert to plain dict
        usage = (
            resp.usage.model_dump()
            if hasattr(resp.usage, "model_dump")
            else dict(resp.usage)
        )  # type: ignore

    return {
        "session": req.sessionId,
        "model": req.model,
        "reply": text,
        "temperature": req.temperature,
        "latency_ms": latency_ms,
        "usage": _normalize_usage(usage),
        "version": VERSION,
    }


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest):
    """
    Streaming chat as Server-Sent Events (SSE-like). Still POST so the UI can
    send the same JSON body; response is `text/event-stream`.

    Events:
      - data: {"delta": "<token chunk>"}                # many
      - event: done\ndata: { final, latency_ms, ... }   # once at end
      - event: error\ndata: { error, version }          # on error
    """
    _ = _require_client()  # validate api key now

    def gen():
        c = _require_client()
        start = time.perf_counter()
        full: List[str] = []
        usage_dict: Optional[Dict[str, Any]] = None

        try:
            stream = c.chat.completions.create(
                **_chat_kwargs(req),
                stream=True,
                stream_options={"include_usage": True},
            )

            for chunk in stream:
                # token deltas
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta and getattr(delta, "content", None):
                        token = delta.content
                        full.append(token)
                        yield _sse({"delta": token})

                # usage (only present on final chunk when include_usage=True)
                u = getattr(chunk, "usage", None)
                if u:
                    usage_dict = u.model_dump() if hasattr(u, "model_dump") else dict(u)  # type: ignore

            latency_ms = int((time.perf_counter() - start) * 1000)
            final_text = "".join(full).strip()

            yield _sse(
                {
                    "final": True,
                    "reply": final_text,
                    "latency_ms": latency_ms,
                    "usage": _normalize_usage(usage_dict),
                    "version": VERSION,
                },
                event="done",
            )

        except Exception as e:
            yield _sse(
                {
                    "error": {
                        "type": e.__class__.__name__,
                        "message": str(e),
                    },
                    "version": VERSION,
                },
                event="error",
            )

    return StreamingResponse(gen(), media_type="text/event-stream")
