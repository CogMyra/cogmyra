# server/main.py
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

APP_NAME = "cogmyra-api"

# --- Allowed web origins (prod + local dev) ---
ALLOWED_ORIGINS: List[str] = [
    "https://cogmyra-web-app.onrender.com",  # your Render static site
    "http://localhost:5173",  # vite/dev
    "http://localhost:4321",  # astro/dev
    "http://localhost:3000",  # next/dev
]

app = FastAPI(title=APP_NAME)

# ---- CORS (single source of truth) -----------------------------------------
# No custom preflight handlers, no manual header setting.
# With allow_credentials=False we can safely reflect "*" when needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


# ---- Health ----------------------------------------------------------------
@app.get("/api/health")
def health() -> JSONResponse:
    payload: Dict[str, Any] = {
        "status": "ok",
        "service": APP_NAME,
        "ts": datetime.now(timezone.utc).isoformat(),
        "build": os.getenv("CM_BUILD_TAG", "cors-clean-v1"),
    }
    resp = JSONResponse(payload)
    # helpful for smoke tests so CF/Render don't cache it
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ---- Chat (demo implementation) -------------------------------------------
# Replace this with your real model call if needed.


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    sessionId: str
    messages: List[ChatMessage]


@app.post("/api/chat")
async def chat(req: ChatRequest) -> JSONResponse:
    user_last = next(
        (m.content for m in reversed(req.messages) if m.role == "user"), ""
    )
    reply = "Hello, greetings, hi!" if user_last else "Hi!"
    return JSONResponse({"reply": reply})


# ---- Minimal logs endpoint used by the beta page ---------------------------
@app.get("/api/admin/logs")
def logs(limit: int = 10) -> JSONResponse:
    # stub so the front-end button doesn't error
    return JSONResponse({"entries": [], "limit": limit})
