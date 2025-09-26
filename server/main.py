# server/main.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

APP_NAME = "cogmyra-api"
BUILD_ID = "cors-clean-v1"

# --- Allowed web origins (prod + local dev) ---
ALLOWED_ORIGINS: List[str] = [
    # Prod static site
    "https://cogmyra-web-app.onrender.com",
    # Local dev (Vite) — include the ports you actually use
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://localhost:5184",
    "http://localhost:5185",
]

app = FastAPI(title=APP_NAME)

# CORS (no credentials; simple GET/POST/OPTIONS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    max_age=600,
)

# ---------- Models ----------
Role = Literal["system", "user", "assistant"]


class Message(BaseModel):
    role: Role
    content: str


class ChatRequest(BaseModel):
    sessionId: str
    messages: List[Message]
    model: str | None = None


class ChatResponse(BaseModel):
    reply: str


# ---------- Routes ----------
@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": APP_NAME,
            "ts": datetime.now(timezone.utc).isoformat(),
            "build": BUILD_ID,
        }
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """
    Minimal demo handler.
    """
    # Tiny canned response so the web app has something to show.
    text = req.messages[-1].content.strip().lower() if req.messages else ""
    if text in {"ping", "hi", "hello"}:
        reply = "Hello, greetings, hi!"
    else:
        reply = "Hello, greetings, hi!"
    return ChatResponse(reply=reply)


# Optional root
@app.get("/")
def root() -> JSONResponse:
    return JSONResponse({"service": APP_NAME, "health": "/api/health"})
