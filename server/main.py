# FastAPI app for CogMyra – chat proxy + logging + admin
from __future__ import annotations

import csv
import os
from datetime import datetime
from io import StringIO
from typing import List, Optional

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

# ---- Env ----
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ADMIN_KEY = os.getenv("ADMIN_KEY", "")
CORS_ALLOWED = os.getenv("CORS_ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in CORS_ALLOWED.split(",") if o.strip()] or ["*"]

# ---- App ----
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Models ----
class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str
    messages: List[Message]


class ChatResponse(BaseModel):
    reply: str


class LogRow(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    created_at: datetime


# ---- In-memory log ----
_LOG: List[LogRow] = []
_COUNTER = 0


def _append_log(session_id: str, role: str, content: str) -> None:
    global _COUNTER
    _COUNTER += 1
    _LOG.append(
        LogRow(
            id=_COUNTER,
            session_id=session_id,
            role=role,
            content=content,
            created_at=datetime.utcnow(),
        )
    )


def _require_admin(x_admin_key: Optional[str]) -> None:
    if not ADMIN_KEY or x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


# ---- Health / Diag ----
@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/diag")
def diag():
    return {"has_openai_key": bool(OPENAI_API_KEY), "origins": ALLOWED_ORIGINS}


# ---- Chat ----
@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request):
    user_text = (req.messages[-1].content if req.messages else "").strip()
    _append_log(req.session_id, "user", user_text)

    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Missing OpenAI API key")

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a concise, friendly assistant."},
                {"role": "user", "content": user_text or "Say hello."},
            ],
            temperature=0.7,
            max_tokens=120,
        )
        reply = resp.choices[0].message.content or "…"
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Model error: {e!r}")

    _append_log(req.session_id, "assistant", reply)
    return ChatResponse(reply=reply)


# ---- Admin: stats ----
@app.get("/api/admin/stats")
def admin_stats(x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    total = len(_LOG)
    sessions = {r.session_id for r in _LOG}
    last = _LOG[-1].created_at.isoformat() if _LOG else None
    return {
        "total_rows": total,
        "unique_sessions": len(sessions),
        "last_entry_at": last,
    }


# ---- Admin: export CSV ----
@app.get("/api/admin/export.csv")
@app.get("/api/admin/export")
def admin_export_csv(x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)

    def _gen():
        header = ["id", "session_id", "role", "created_at", "content"]
        buf = StringIO()
        csv.writer(buf).writerow(header)
        yield buf.getvalue()
        for r in _LOG:
            buf = StringIO()
            csv.writer(buf).writerow(
                [r.id, r.session_id, r.role, r.created_at.isoformat(), r.content]
            )
            yield buf.getvalue()

    csv_text = "".join(list(_gen()))
    headers = {"Content-Disposition": 'attachment; filename="logs.csv"'}
    return Response(
        content=csv_text, media_type="text/csv; charset=utf-8", headers=headers
    )


# ---- Admin: recent logs (JSON) ----
@app.get("/api/admin/logs")
def admin_logs(limit: int = 50, x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    limit = max(1, min(500, limit))
    rows = list(reversed(_LOG[-limit:]))
    return [
        {
            "id": r.id,
            "time": r.created_at.isoformat(timespec="seconds"),
            "session": r.session_id,
            "role": r.role,
            "content": r.content,
        }
        for r in rows
    ]
