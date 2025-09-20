import os
import uuid
import csv
from io import StringIO
from datetime import datetime
from typing import List

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openai import OpenAI

# -------------------------------------------------------------------
# Environment
# -------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ADMIN_KEY = os.getenv("ADMIN_KEY", "")
CORS_ALLOWED = (
    os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if os.getenv("CORS_ALLOWED_ORIGINS")
    else []
)

# -------------------------------------------------------------------
# App setup
# -------------------------------------------------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=OPENAI_API_KEY)


# -------------------------------------------------------------------
# Models
# -------------------------------------------------------------------
class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str
    messages: List[Message]


class ChatResponse(BaseModel):
    reply: str


class LogRow(BaseModel):
    id: str
    session_id: str
    role: str
    created_at: datetime
    content: str


_LOG: List[LogRow] = []


# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="No OpenAI key configured")

    # Log incoming messages
    for m in req.messages:
        _LOG.append(
            LogRow(
                id=str(uuid.uuid4()),
                session_id=req.session_id,
                role=m.role,
                created_at=datetime.utcnow(),
                content=m.content,
            )
        )

    # Call OpenAI
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[m.dict() for m in req.messages],
            max_tokens=200,
        )
        reply = resp.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI error: {e}")

    # Log assistant reply
    _LOG.append(
        LogRow(
            id=str(uuid.uuid4()),
            session_id=req.session_id,
            role="assistant",
            created_at=datetime.utcnow(),
            content=reply,
        )
    )

    return ChatResponse(reply=reply)


@app.get("/api/diag")
def diag():
    return {
        "has_openai_key": bool(OPENAI_API_KEY),
        "origins": CORS_ALLOWED or ["*"],
    }


@app.get("/api/admin/stats")
def admin_stats(x_admin_key: str = Header("")):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    return {
        "total_rows": len(_LOG),
        "unique_sessions": len({r.session_id for r in _LOG}),
        "last_entry_at": _LOG[-1].created_at.isoformat() if _LOG else None,
    }


def _csv_stream():
    # header
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "session_id", "role", "created_at", "content"])
    yield buf.getvalue()
    # rows
    for r in _LOG:
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [r.id, r.session_id, r.role, r.created_at.isoformat(), r.content]
        )
        yield buf.getvalue()


# Primary CSV endpoint (no extension)
@app.get("/api/admin/export")
def admin_export(x_admin_key: str = Header("")):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    return StreamingResponse(
        _csv_stream(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=logs.csv"},
    )


# Alias to match the web UI button calling `/api/admin/export.csv`
@app.get("/api/admin/export.csv")
def admin_export_csv(x_admin_key: str = Header("")):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    return StreamingResponse(
        _csv_stream(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=logs.csv"},
    )
