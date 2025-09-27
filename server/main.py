import json
import logging
import os
import time
import uuid
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel

# ---- Version bump -----------------------------------------------------------
VERSION = "api-v5-stream"

# ---- FastAPI app ------------------------------------------------------------
app = FastAPI(title="CogMyra API", version=VERSION)

# ---- CORS -------------------------------------------------------------------
# Allow prod origin(s) + localhost dev ports, configurable via env
CORS_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS if o.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Logging ---------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",  # log JSON directly
)


def _log_line(data: dict) -> None:
    try:
        logging.info(json.dumps(data, ensure_ascii=False))
    except Exception:
        pass


def set_request_context(
    request: Request, *, model: str | None = None, usage_total: int | None = None
) -> None:
    if model is not None:
        request.state.model = model
    if usage_total is not None:
        request.state.usage_total_tokens = usage_total


@app.middleware("http")
async def log_requests(request: Request, call_next):
    rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex
    request.state.request_id = rid

    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = getattr(response, "status_code", 500)
        return response
    finally:
        latency_ms = int((time.perf_counter() - start) * 1000)
        origin = request.headers.get("origin") or "-"
        _log_line(
            {
                "request_id": rid,
                "path": request.url.path,
                "method": request.method,
                "origin": origin,
                "status": status,
                "latency_ms": latency_ms,
                "model": getattr(request.state, "model", None),
                "tokens": getattr(request.state, "usage_total_tokens", None),
            }
        )


# ---- OpenAI setup -----------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY in environment")

oai = OpenAI(api_key=OPENAI_API_KEY)


# ---- Schemas ----------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    sessionId: str
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7


# ---- Health -----------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": "true", "version": VERSION}


# ---- Chat (non-stream) ------------------------------------------------------
@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server missing OPENAI_API_KEY")

    start = time.perf_counter()
    try:
        resp = oai.chat.completions.create(
            model=req.model,
            messages=[{"role": m.role, "content": m.content} for m in req.messages],
            temperature=req.temperature,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI error: {e}")

    reply = resp.choices[0].message.content
    latency_ms = int((time.perf_counter() - start) * 1000)

    usage = resp.usage
    total_tokens = usage.total_tokens if usage else None

    set_request_context(request, model=req.model, usage_total=total_tokens)

    return {
        "reply": reply,
        "version": VERSION,
        "latency_ms": latency_ms,
        "usage": usage.model_dump() if usage else {},
    }


# ---- Chat (SSE stream) ------------------------------------------------------
def _sse_line(obj: dict | str, *, event: str | None = None) -> bytes:
    if event:
        return (f"event: {event}\n" + f"data: {json.dumps(obj)}\n\n").encode("utf-8")
    return (f"data: {json.dumps(obj)}\n\n").encode("utf-8")


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, request: Request):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server missing OPENAI_API_KEY")

    set_request_context(request, model=req.model)
    start = time.perf_counter()

    def gen():
        try:
            stream = oai.chat.completions.create(
                model=req.model,
                messages=[{"role": m.role, "content": m.content} for m in req.messages],
                temperature=req.temperature,
                stream=True,
            )
            full_text = []
            for event in stream:
                piece = event.choices[0].delta.content or ""
                if piece:
                    full_text.append(piece)
                    yield _sse_line({"delta": piece})
            reply = "".join(full_text)
            latency_ms = int((time.perf_counter() - start) * 1000)

            usage = getattr(stream, "usage", None)
            usage_dict = (
                usage.model_dump() if hasattr(usage, "model_dump") else {}
            ) or {}

            set_request_context(request, usage_total=usage_dict.get("total_tokens"))

            yield _sse_line(
                {
                    "final": True,
                    "reply": reply,
                    "latency_ms": latency_ms,
                    "usage": usage_dict,
                    "version": VERSION,
                },
                event="done",
            )
        except Exception as e:
            yield _sse_line({"error": str(e)}, event="error")

    return StreamingResponse(gen(), media_type="text/event-stream")
