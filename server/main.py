import os
import csv
from io import StringIO
from datetime import datetime
from typing import List

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

# --- Config ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_KEY = os.getenv("ADMIN_KEY", "changeme")
CORS_ALLOWED = (
    os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if os.getenv("CORS_ALLOWED_ORIGINS")
    else ["*"]
)

# --- App ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- In-memory log ---
class LogEntry(BaseModel):
    id: int
    session_id: str
    role: str
    created_at: datetime
    content: str


_LOG: List[LogEntry] = []
_NEXT_ID = 1


def log_message(session_id: str, role: str, content: str):
    global _NEXT_ID
    entry = LogEntry(
        id=_NEXT_ID,
        session_id=session_id,
        role=role,
        created_at=datetime.utcnow(),
        content=content,
    )
    _LOG.append(entry)
    _NEXT_ID += 1


# --- Schemas ---
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str
    messages: List[ChatMessage]


class ChatResponse(BaseModel):
    reply: str


# --- Routes ---
@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    log_message(
        req.session_id, "user", req.messages[-1].content if req.messages else ""
    )

    if not OPENAI_API_KEY:
        reply = f"(Temporary fallback) You said: {req.messages[-1].content if req.messages else ''}"
    else:
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": m.role, "content": m.content} for m in req.messages],
                max_tokens=200,
            )
            reply = completion.choices[0].message.content
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    log_message(req.session_id, "assistant", reply)
    return ChatResponse(reply=reply)


@app.get("/api/admin/stats")
def admin_stats(request: Request):
    key = request.headers.get("x-admin-key")
    if key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

    return {
        "total_rows": len(_LOG),
        "unique_sessions": len(set(r.session_id for r in _LOG)),
        "last_entry_at": _LOG[-1].created_at.isoformat() if _LOG else None,
    }


@app.get("/api/admin/logs")
def admin_logs(request: Request):
    key = request.headers.get("x-admin-key")
    if key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

    def _gen():
        for r in _LOG:
            buf = StringIO()
            writer = csv.writer(buf)
            writer.writerow(
                [r.id, r.session_id, r.role, r.created_at.isoformat(), r.content]
            )
            yield buf.getvalue()

    return Response(
        content="".join(list(_gen())),
        media_type="text/csv; charset=utf-8",
    )


@app.get("/api/diag")
def diag():
    return {
        "has_openai_key": bool(OPENAI_API_KEY),
        "origins": CORS_ALLOWED or ["*"],
    }
