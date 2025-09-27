# server/main.py
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Generator, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from openai import (
    OpenAI,
    OpenAIError,
    AuthenticationError,
    RateLimitError,
    NotFoundError,
    BadRequestError,
    APIStatusError,
)
from pydantic import BaseModel, Field

# --------------------------------------------------------------------------------------
# App/version
# --------------------------------------------------------------------------------------

VERSION = "api-v5.3-errors"

app = FastAPI(title="CogMyra API", version=VERSION)

# --------------------------------------------------------------------------------------
# Env / Config
# --------------------------------------------------------------------------------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
INBOUND_API_KEY = os.getenv("INBOUND_API_KEY", "").strip()

# CORS: allow env allowlist + localhost:* (no credentials)
CORS_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS else [],
    allow_origin_regex=r"^https?://localhost(?::\d+)?$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAI client
oai: Optional[OpenAI] = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Logger
logger = logging.getLogger("uvicorn.error")


# --------------------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str = Field(..., description="user|assistant|system")
    content: str


class ChatRequest(BaseModel):
    sessionId: str
    model: str
    messages: list[ChatMessage]
    temperature: float | None = 0.2


# --------------------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------------------


def json_error(
    status_code: int, code: str, message: str, request_id: str | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}, "request_id": request_id},
    )


def require_inbound_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    if INBOUND_API_KEY and (not x_api_key or x_api_key != INBOUND_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        )


def _usage_to_dict(usage: Any) -> dict:
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    try:
        return dict(usage)  # type: ignore[arg-type]
    except Exception:
        return {}


def _sse_line(obj: dict | str, *, event: str | None = None) -> bytes:
    if event:
        return (f"event: {event}\n" + f"data: {json.dumps(obj)}\n\n").encode("utf-8")
    return (f"data: {json.dumps(obj)}\n\n").encode("utf-8")


# --------------------------------------------------------------------------------------
# Middleware: structured request logging
# --------------------------------------------------------------------------------------


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    started = time.perf_counter()
    model_hint = ""
    try:
        if request.url.path.startswith("/api/chat"):
            body = await request.body()
            if body:
                try:
                    payload = json.loads(body.decode("utf-8"))
                    model_hint = payload.get("model", "")
                except Exception:
                    pass
        response = await call_next(request)
        return response
    finally:
        took_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            json.dumps(
                {
                    "path": request.url.path,
                    "method": request.method,
                    "origin": request.headers.get("origin", ""),
                    "model": model_hint,
                    "latency_ms": took_ms,
                }
            )
        )


# --------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    return {"ok": "true", "version": VERSION}


@app.post("/api/chat", dependencies=[Depends(require_inbound_key)])
def chat(req: ChatRequest):
    """
    Success: { reply, latency_ms, usage, version }
    Error:   { "error": { "code", "message" }, "request_id": <id|null> }
    """
    if not OPENAI_API_KEY:
        return json_error(
            500, "SERVER_MISCONFIG", "Server missing OPENAI_API_KEY.", None
        )
    if oai is None:
        return json_error(500, "SERVER_INIT", "OpenAI client not initialized.", None)

    start = time.perf_counter()
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    try:
        completion = oai.chat.completions.create(
            model=req.model,
            messages=messages,
            temperature=req.temperature,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        reply = completion.choices[0].message.content if completion.choices else ""
        usage = _usage_to_dict(getattr(completion, "usage", None))
        return {
            "reply": reply,
            "latency_ms": latency_ms,
            "usage": usage,
            "version": VERSION,
        }

    # Standardized error mapping (do NOT raise; return envelope)
    except AuthenticationError as e:
        return json_error(
            401,
            "UPSTREAM_AUTH",
            "Upstream authentication failed. Check OPENAI_API_KEY.",
            getattr(e, "request_id", None),
        )
    except RateLimitError as e:
        return json_error(
            429,
            "UPSTREAM_RATE_LIMIT",
            "Upstream rate limit exceeded. Please retry later.",
            getattr(e, "request_id", None),
        )
    except NotFoundError as e:
        return json_error(
            400,
            "MODEL_NOT_FOUND",
            "The requested model was not found or you do not have access to it.",
            getattr(e, "request_id", None),
        )
    except BadRequestError as e:
        return json_error(
            400, "UPSTREAM_BAD_REQUEST", str(e), getattr(e, "request_id", None)
        )
    except APIStatusError as e:
        status_code = int(getattr(e, "status_code", 502) or 502)
        if 500 <= status_code < 600:
            return json_error(
                502,
                "UPSTREAM_5XX",
                "Upstream service error. Please try again.",
                getattr(e, "request_id", None),
            )
        return json_error(400, "UPSTREAM_ERROR", str(e), getattr(e, "request_id", None))
    except OpenAIError as e:
        return json_error(502, "UPSTREAM_ERROR", str(e), getattr(e, "request_id", None))
    except Exception:
        return json_error(500, "INTERNAL", "Unexpected server error.", None)


@app.post("/api/chat/stream", dependencies=[Depends(require_inbound_key)])
def chat_stream(req: ChatRequest):
    """
    SSE stream:
      data: {"delta": "<chunk>"} (many)
      event: done
      data: {"final": true, "reply": "...", "latency_ms": ..., "usage": {...}, "version": VERSION}
    On failure before stream starts, emits one "error" event.
    """
    if not OPENAI_API_KEY or oai is None:

        def fail_gen():
            yield _sse_line(
                {
                    "error": {
                        "code": "SERVER_MISCONFIG",
                        "message": "Server missing OPENAI_API_KEY.",
                    }
                },
                event="error",
            )

        return StreamingResponse(fail_gen(), media_type="text/event-stream")

    start = time.perf_counter()
    msgs = [{"role": m.role, "content": m.content} for m in req.messages]

    def gen() -> Generator[bytes, None, None]:
        try:
            stream = oai.chat.completions.create(
                model=req.model,
                messages=msgs,
                temperature=req.temperature,
                stream=True,
            )
            parts: list[str] = []
            for event in stream:
                piece = event.choices[0].delta.content or ""
                if piece:
                    parts.append(piece)
                    yield _sse_line({"delta": piece})

            reply = "".join(parts)
            latency_ms = int((time.perf_counter() - start) * 1000)
            usage = _usage_to_dict(getattr(stream, "usage", None))
            yield _sse_line(
                {
                    "final": True,
                    "reply": reply,
                    "latency_ms": latency_ms,
                    "usage": usage,
                    "version": VERSION,
                },
                event="done",
            )

        except NotFoundError as e:
            yield _sse_line(
                {
                    "error": {
                        "code": "MODEL_NOT_FOUND",
                        "message": "The requested model was not found or you do not have access to it.",
                    },
                    "request_id": getattr(e, "request_id", None),
                },
                event="error",
            )
        except AuthenticationError as e:
            yield _sse_line(
                {
                    "error": {
                        "code": "UPSTREAM_AUTH",
                        "message": "Upstream authentication failed. Check OPENAI_API_KEY.",
                    },
                    "request_id": getattr(e, "request_id", None),
                },
                event="error",
            )
        except RateLimitError as e:
            yield _sse_line(
                {
                    "error": {
                        "code": "UPSTREAM_RATE_LIMIT",
                        "message": "Upstream rate limit exceeded. Please retry later.",
                    },
                    "request_id": getattr(e, "request_id", None),
                },
                event="error",
            )
        except BadRequestError as e:
            yield _sse_line(
                {
                    "error": {"code": "UPSTREAM_BAD_REQUEST", "message": str(e)},
                    "request_id": getattr(e, "request_id", None),
                },
                event="error",
            )
        except APIStatusError as e:
            status_code = int(getattr(e, "status_code", 502) or 502)
            code = "UPSTREAM_5XX" if 500 <= status_code < 600 else "UPSTREAM_ERROR"
            msg = (
                "Upstream service error. Please try again."
                if code == "UPSTREAM_5XX"
                else str(e)
            )
            yield _sse_line(
                {
                    "error": {"code": code, "message": msg},
                    "request_id": getattr(e, "request_id", None),
                },
                event="error",
            )
        except OpenAIError as e:
            yield _sse_line(
                {
                    "error": {"code": "UPSTREAM_ERROR", "message": str(e)},
                    "request_id": getattr(e, "request_id", None),
                },
                event="error",
            )
        except Exception:
            yield _sse_line(
                {"error": {"code": "INTERNAL", "message": "Unexpected server error."}},
                event="error",
            )

    return StreamingResponse(gen(), media_type="text/event-stream")
