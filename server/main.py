from __future__ import annotations

import os
from typing import List

from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# ---------------------------
# FastAPI app + CORS
# ---------------------------
app = FastAPI(title="CogMyra API")

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5185",
    "http://localhost:5186",
    "https://cogmyra-api.onrender.com",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],  # includes x-admin-key, Content-Type, etc.
)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


# ---------------------------
# Models
# ---------------------------
class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str
    messages: List[Message]


class ChatResponse(BaseModel):
    reply: str


# ---------------------------
# Routes
# ---------------------------
@app.get("/api/health")
async def health():
    return {"ok": True}


# --- Admin: support GET and POST for convenience ---
async def _check_admin(request: Request) -> None:
    key = request.headers.get("x-admin-key", "")
    if not ADMIN_PASSWORD or key != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/api/admin/stats")
async def admin_stats_get(request: Request):
    await _check_admin(request)
    return {
        "total_rows": 6,
        "unique_sessions": 3,
        "last_entry_at": "2025-09-16T22:29:54.931190",
    }


@app.post("/api/admin/stats")
async def admin_stats_post(request: Request):
    return await admin_stats_get(request)


@app.get("/api/admin/export.csv")
async def admin_export_get(request: Request):
    await _check_admin(request)
    # Placeholder CSV; swap in real data later
    csv = (
        "id,session_id,role,created_at,content\n"
        "1,web-test,user,2025-09-18T00:00:00Z,Hello\n"
        "2,web-test,assistant,2025-09-18T00:00:01Z,Hi there!\n"
    )
    return Response(content=csv, media_type="text/csv")


@app.post("/api/admin/export.csv")
async def admin_export_post(request: Request):
    return await admin_export_get(request)


# --- Chat: POST (primary) + a simple GET for smoke tests ---
@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    last_user = next(
        (m.content for m in reversed(req.messages) if m.role == "user"), ""
    )
    reply = (
        "Hello! I'm alive on Render and received your message"
        + (f": “{last_user}”." if last_user else ".")
        + " (This is an echo placeholder—you can swap in OpenAI next.)"
    )
    return {"reply": reply}


@app.get("/api/chat", response_model=ChatResponse)
async def chat_get(session_id: str = "browser", content: str = "Ping"):
    return {"reply": f"Pong (GET)! You said: {content}"}
