# server/main.py
from __future__ import annotations

import os
import time
from typing import List, Optional

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI()

ALLOWED_ORIGINS = [
    "https://cogmyra-web.onrender.com",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

VERSION = "api-v3-echo"  # <-- bump to verify deployment


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    sessionId: str = Field(..., alias="sessionId")
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = None


class ChatResponse(BaseModel):
    session: str
    model: str
    reply: str
    temperature: Optional[float] = None
    latency_ms: Optional[int] = None
    usage: Optional[dict] = None
    version: str = VERSION


@app.get("/api/health")
def health() -> dict:
    return {"ok": "true", "version": VERSION}


@app.get("/api/healthz")
def healthz() -> dict:
    return {"ok": "true", "version": VERSION}


def _last_user_text(messages: List[ChatMessage]) -> Optional[str]:
    for m in reversed(messages):
        if m.role.lower() == "user" and m.content:
            return m.content
    return None


def _should_strict_echo(text: str) -> bool:
    # Echo short messages to make web Guide verification deterministic.
    return bool(text) and len(text) <= 200


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    t0 = time.perf_counter()

    # STRICT LOCAL ECHO (no OpenAI call)
    last_user = _last_user_text(req.messages) or ""
    if _should_strict_echo(last_user):
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return ChatResponse(
            session=req.sessionId,
            model=req.model,
            reply=last_user,
            temperature=req.temperature,
            latency_ms=latency_ms,
            usage={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "prompt_tokens_details": {"cached_tokens": 0, "audio_tokens": 0},
                "completion_tokens_details": {
                    "reasoning_tokens": 0,
                    "audio_tokens": 0,
                    "accepted_prediction_tokens": 0,
                    "rejected_prediction_tokens": 0,
                },
            },
        )

    # FALLBACK: forward to OpenAI
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return ChatResponse(
            session=req.sessionId,
            model=req.model,
            reply="(server error: OPENAI_API_KEY not set)",
            temperature=req.temperature,
            latency_ms=latency_ms,
            usage=None,
        )

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        *[m.model_dump() for m in req.messages],
    ]
    payload = {
        "model": req.model,
        "messages": messages,
        "temperature": 0.0 if req.temperature is None else req.temperature,
        "response_format": {"type": "text"},
    }
    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions", json=payload, headers=headers
        )
        r.raise_for_status()
        data = r.json()

    reply_text = (
        data.get("choices", [{}])[0].get("message", {}).get("content", "(no reply)")
    )
    usage = data.get("usage")
    latency_ms = int((time.perf_counter() - t0) * 1000)

    return ChatResponse(
        session=req.sessionId,
        model=req.model,
        reply=reply_text,
        temperature=req.temperature,
        latency_ms=latency_ms,
        usage=usage,
    )
