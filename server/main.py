# server/main.py
from __future__ import annotations

# --- stdlib
import os
import time
from typing import List, Optional

# --- third-party (keep imports at top to satisfy Ruff E402)
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI

# ---- App + CORS -------------------------------------------------------------
app = FastAPI()
VERSION = "api-v4-openai"  # bump to confirm deploy

ALLOWED_ORIGINS = [
    "https://cogmyra-web.onrender.com",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
    "http://localhost:5176",
    "http://127.0.0.1:5176",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Schemas ----------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str


class UsageDetails(BaseModel):
    cached_tokens: int = 0
    audio_tokens: int = 0
    reasoning_tokens: int = 0
    accepted_prediction_tokens: int = 0
    rejected_prediction_tokens: int = 0


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_tokens_details: UsageDetails = Field(default_factory=UsageDetails)
    completion_tokens_details: UsageDetails = Field(default_factory=UsageDetails)


class ChatRequest(BaseModel):
    sessionId: str
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7


class ChatResponse(BaseModel):
    session: str
    model: str
    reply: str
    temperature: float
    latency_ms: int
    usage: Usage
    version: str


# ---- Health -----------------------------------------------------------------
@app.get("/api/health")
@app.get("/api/healthz")
def health():
    return {"ok": "true", "version": VERSION}


# ---- Chat (OpenAI) ----------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, _request: Request):
    start = time.time()

    # Fallback if key is missing: echo last user message
    if client is None:
        reply_text = req.messages[-1].content if req.messages else ""
        latency_ms = int((time.time() - start) * 1000)
        return ChatResponse(
            session=req.sessionId,
            model=req.model,
            reply=reply_text,
            temperature=req.temperature or 0.7,
            latency_ms=latency_ms,
            usage=Usage(),
            version=VERSION,
        )

    # Convert to OpenAI format
    openai_messages = [{"role": m.role, "content": m.content} for m in req.messages]

    # Call OpenAI Chat Completions API (keeps your response shape)
    resp = client.chat.completions.create(
        model=req.model,
        messages=openai_messages,
        temperature=req.temperature or 0.7,
    )

    choice = resp.choices[0]
    reply_text = (choice.message.content or "").strip()

    # Usage (may be None on some responses)
    prompt_tokens = getattr(resp.usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(resp.usage, "completion_tokens", 0) or 0
    total_tokens = (
        getattr(resp.usage, "total_tokens", prompt_tokens + completion_tokens) or 0
    )

    latency_ms = int((time.time() - start) * 1000)

    return ChatResponse(
        session=req.sessionId,
        model=req.model,
        reply=reply_text,
        temperature=req.temperature or 0.7,
        latency_ms=latency_ms,
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
        version=VERSION,
    )
