from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from openai import AuthenticationError, NotFoundError, OpenAI, OpenAIError
from pydantic import BaseModel, Field

# ------------------------------------------------------------------------------
# Version
# ------------------------------------------------------------------------------
VERSION = "api-v5.6-health"

# ------------------------------------------------------------------------------
# Config / Env
# ------------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SERVER_API_KEY = os.getenv("SERVER_API_KEY", "")
CORS_ORIGINS_ENV = os.getenv("CORS_ORIGINS", "")

# CORS allowlist: prod URLs + any localhost:* (no credentials)
_default_localhost = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1",
]
_allow_from_env = [o.strip() for o in CORS_ORIGINS_ENV.split(",") if o.strip()]
CORS_ALLOWLIST = list({*_default_localhost, *_allow_from_env})

# ------------------------------------------------------------------------------
# App
# ------------------------------------------------------------------------------
app = FastAPI(title="CogMyra API", version=VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWLIST or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


# ------------------------------------------------------------------------------
# Models / Schemas
# ------------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    sessionId: str = Field(default="default")
    model: str = Field(default="gpt-4o-mini")
    messages: List[ChatMessage]
    temperature: float = Field(default=0.2)


class ChatResponse(BaseModel):
    reply: str
    version: str
    latency_ms: int
    usage: Dict[str, int] | Dict[str, Dict[str, int]]
    request_id: Optional[str] = None


class ErrorEnvelope(BaseModel):
    error: Dict[str, str]
    request_id: Optional[str] = None


# ------------------------------------------------------------------------------
# Simple in-memory sessions (last N messages per sessionId)
# ------------------------------------------------------------------------------
_MAX_HISTORY = 16
_sessions: Dict[str, Deque[Dict[str, str]]] = defaultdict(
    lambda: deque(maxlen=_MAX_HISTORY)
)


def get_oai_client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server missing OPENAI_API_KEY")
    return OpenAI(api_key=OPENAI_API_KEY)


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    if not SERVER_API_KEY:
        # If no server key configured, allow all (useful for local dev)
        return
    if not x_api_key or x_api_key != SERVER_API_KEY:
        raise HTTPException(
            status_code=401, detail="Unauthorized: missing or invalid API key"
        )


# ------------------------------------------------------------------------------
# Logging helper
# ------------------------------------------------------------------------------
@app.middleware("http")
async def log_latency(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
        return response
    finally:
        dur_ms = int((time.perf_counter() - start) * 1000)
        origin = request.headers.get("origin", "")
        model = ""
        try:
            if request.method == "POST" and request.url.path.startswith("/api/chat"):
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


# ------------------------------------------------------------------------------
# Health
# ------------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": "true", "version": VERSION}


@app.get("/api/health/full", response_class=JSONResponse)
def health_full():
    """
    Extended health:
      - server/versions
      - env presence (not values)
      - upstream OpenAI reachability via models.list()
    """
    env_ok = {
        "OPENAI_API_KEY": bool(OPENAI_API_KEY),
        "SERVER_API_KEY": bool(SERVER_API_KEY),
    }
    upstream = {"openai": "unknown", "error": None}

    if OPENAI_API_KEY:
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            _ = client.models.list()  # lightweight ping
            upstream["openai"] = "ok"
        except AuthenticationError as e:
            upstream["openai"] = "auth_error"
            upstream["error"] = str(e)
        except OpenAIError as e:
            upstream["openai"] = "unavailable"
            upstream["error"] = str(e)
        except Exception as e:
            upstream["openai"] = "error"
            upstream["error"] = str(e)
    else:
        upstream["openai"] = "missing_api_key"

    return JSONResponse(
        {"ok": True, "version": VERSION, "env": env_ok, "upstream": upstream}
    )


# ------------------------------------------------------------------------------
# Chat (non-streaming)
# ------------------------------------------------------------------------------
@app.post("/api/chat", response_class=JSONResponse)
def chat(req: ChatRequest, _: None = Depends(require_api_key)):
    client = get_oai_client()

    # merge session history + new messages
    history = list(_sessions[req.sessionId])
    payload_messages = [
        {"role": m["role"], "content": m["content"]} for m in history
    ] + [{"role": m.role, "content": m.content} for m in req.messages]

    start = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=req.model,
            messages=payload_messages,
            temperature=req.temperature,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)

        reply = resp.choices[0].message.content or ""
        request_id = getattr(resp, "id", None)
        usage = getattr(resp, "usage", None)
        usage_dict = (
            usage.model_dump() if hasattr(usage, "model_dump") else (usage or {})
        )

        # update session history (append user + assistant from this turn)
        for m in req.messages:
            _sessions[req.sessionId].append({"role": m.role, "content": m.content})
        _sessions[req.sessionId].append({"role": "assistant", "content": reply})

        return JSONResponse(
            ChatResponse(
                reply=reply,
                version=VERSION,
                latency_ms=latency_ms,
                usage=usage_dict,
                request_id=request_id,
            ).model_dump()
        )

    except NotFoundError:
        return JSONResponse(
            ErrorEnvelope(
                error={
                    "code": "MODEL_NOT_FOUND",
                    "message": "The requested model was not found or you do not have access to it.",
                },
                request_id=None,
            ).model_dump(),
            status_code=404,
        )
    except AuthenticationError:
        return JSONResponse(
            ErrorEnvelope(
                error={
                    "code": "UPSTREAM_AUTH",
                    "message": "Upstream authentication failed.",
                },
                request_id=None,
            ).model_dump(),
            status_code=502,
        )
    except OpenAIError as e:
        return JSONResponse(
            ErrorEnvelope(
                error={"code": "UPSTREAM_ERROR", "message": f"OpenAI error: {str(e)}"},
                request_id=None,
            ).model_dump(),
            status_code=502,
        )
    except Exception as e:
        return JSONResponse(
            ErrorEnvelope(
                error={"code": "SERVER_ERROR", "message": str(e)},
                request_id=None,
            ).model_dump(),
            status_code=500,
        )


# ------------------------------------------------------------------------------
# Chat (streaming SSE)
# ------------------------------------------------------------------------------
def _sse_line(obj: dict | str, *, event: str | None = None) -> bytes:
    if event:
        return (f"event: {event}\n" f"data: {json.dumps(obj)}\n\n").encode("utf-8")
    return (f"data: {json.dumps(obj)}\n\n").encode("utf-8")


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, _: None = Depends(require_api_key)):
    client = get_oai_client()

    history = list(_sessions[req.sessionId])
    payload_messages = [
        {"role": m["role"], "content": m["content"]} for m in history
    ] + [{"role": m.role, "content": m.content} for m in req.messages]

    start = time.perf_counter()

    def gen():
        try:
            stream = client.chat.completions.create(
                model=req.model,
                messages=payload_messages,
                temperature=req.temperature,
                stream=True,
            )
            full_text: List[str] = []
            request_id: Optional[str] = getattr(stream, "id", None)

            for event in stream:
                piece = event.choices[0].delta.content or ""
                if piece:
                    full_text.append(piece)
                    yield _sse_line({"delta": piece})

            reply = "".join(full_text)
            latency_ms = int((time.perf_counter() - start) * 1000)
            usage = getattr(stream, "usage", None)
            usage_dict = (
                usage.model_dump() if hasattr(usage, "model_dump") else (usage or {})
            )

            # update session
            for m in req.messages:
                _sessions[req.sessionId].append({"role": m.role, "content": m.content})
            _sessions[req.sessionId].append({"role": "assistant", "content": reply})

            yield _sse_line(
                {
                    "final": True,
                    "reply": reply,
                    "latency_ms": latency_ms,
                    "usage": usage_dict,
                    "version": VERSION,
                    "request_id": request_id,
                },
                event="done",
            )
        except NotFoundError:
            yield _sse_line(
                {
                    "error": {
                        "code": "MODEL_NOT_FOUND",
                        "message": "The requested model was not found or you do not have access to it.",
                    }
                },
                event="error",
            )
        except AuthenticationError:
            yield _sse_line(
                {
                    "error": {
                        "code": "UPSTREAM_AUTH",
                        "message": "Upstream authentication failed.",
                    }
                },
                event="error",
            )
        except OpenAIError as e:
            yield _sse_line(
                {
                    "error": {
                        "code": "UPSTREAM_ERROR",
                        "message": f"OpenAI error: {str(e)}",
                    }
                },
                event="error",
            )
        except Exception as e:
            yield _sse_line(
                {"error": {"code": "SERVER_ERROR", "message": str(e)}},
                event="error",
            )

    return StreamingResponse(gen(), media_type="text/event-stream")


# ------------------------------------------------------------------------------
# Session admin
# ------------------------------------------------------------------------------
class SessionResetRequest(BaseModel):
    sessionId: str


@app.post("/api/session/reset")
def session_reset(req: SessionResetRequest, _: None = Depends(require_api_key)):
    _sessions.pop(req.sessionId, None)
    return {"ok": True, "sessionId": req.sessionId, "version": VERSION}
