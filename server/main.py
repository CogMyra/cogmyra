from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import io
import csv
import os

app = FastAPI()

# CORS setup
origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://localhost:5176",
    "http://localhost:5177",
    "http://localhost:5178",
    "http://localhost:5179",
    "http://localhost:5180",
    "http://localhost:5181",
    "http://localhost:5185",
    "https://cogmyra-web.onrender.com",  # <-- Replace with your actual Render Static Site URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Simple models
class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str
    messages: list[Message]


# Health check
@app.get("/api/health")
async def health():
    return {"ok": True}


# Chat endpoint (POST)
@app.post("/api/chat")
async def chat(req: ChatRequest):
    last_message = req.messages[-1].content if req.messages else ""
    if last_message.lower() == "ping":
        return {"reply": "Pong! How can I assist you today?"}
    return {"reply": f"You said: {last_message}"}


# Admin key from env or hardcoded
ADMIN_KEY = os.getenv("ADMIN_PASSWORD", "walnut-salsa-meteor-88")


@app.get("/api/admin/stats")
async def admin_stats(request: Request):
    key = request.headers.get("x-admin-key")
    if key != ADMIN_KEY:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    # Dummy stats for now
    return {
        "total_rows": 8,
        "unique_sessions": 4,
        "last_entry_at": "2025-09-20T01:14:31.112921",
    }


@app.get("/api/admin/export.csv")
async def admin_export(request: Request):
    key = request.headers.get("x-admin-key")
    if key != ADMIN_KEY:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    # Fake data — replace with your DB queries later
    rows = [
        ["id", "session_id", "role", "created_at", "content"],
        [1, "demo", "user", "2025-09-16 22:11:04", "Say hello in five words."],
        [2, "demo", "assistant", "2025-09-16 22:11:05", "Hello there! How are you?"],
    ]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=export.csv"},
    )
