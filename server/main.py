# server/main.py
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal, Optional
import time

app = FastAPI()

# ---- CORS (allow dev ports 5173–5176 and the deployed web) ----
ALLOWED_ORIGINS: List[str] = [
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

# ---- Models ----
Role = Literal["system", "user", "assistant"]


class Message(BaseModel):
    role: Role
    content: str


class ChatRequest(BaseModel):
    sessionId: str
    model: str
    messages: List[Message]
    temperature: Optional[float] = 1.0


class ChatResponseUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_tokens_details: dict = {"cached_tokens": 0, "audio_tokens": 0}
    completion_tokens_details: dict = {
        "reasoning_tokens": 0,
        "audio_tokens": 0,
        "accepted_prediction_tokens": 0,
        "rejected_prediction_tokens": 0,
    }


class ChatResponse(BaseModel):
    session: str
    model: str
    reply: str
    temperature: float
    latency_ms: int
    usage: ChatResponseUsage
    version: str


VERSION = "api-v3-echo"


# ---- Health ----
@app.get("/api/health")
async def health():
    return {"ok": "true", "version": VERSION}


# ---- Chat (simple echo so you can test the web) ----
@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    t0 = time.perf_counter()

    # Take the last user message and echo it back verbatim (testing mode)
    last_user = next((m for m in reversed(req.messages) if m.role == "user"), None)
    reply_text = last_user.content if last_user else ""

    latency_ms = int((time.perf_counter() - t0) * 1000)
    return ChatResponse(
        session=req.sessionId,
        model=req.model,
        reply=reply_text,
        temperature=float(req.temperature or 1.0),
        latency_ms=latency_ms,
        usage=ChatResponseUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        version=VERSION,
    )
