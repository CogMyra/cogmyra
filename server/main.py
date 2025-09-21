from __future__ import annotations

import csv
import os
from datetime import datetime
from io import StringIO
from typing import List, Literal, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from openai import OpenAI
from pydantic import BaseModel


# -----------------------------
# Config (env-driven)
# -----------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ADMIN_KEY = os.getenv("ADMIN_KEY", "walnut-salsa-meteor-88")

# Comma-separated list of allowed origins, or single origin
_CORS = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
CORS_ALLOWED: list[str] = (
    [o.strip() for o in _CORS.split(",") if o.strip()] if _CORS else []
)


# -----------------------------
# App
# -----------------------------
app = FastAPI(title="CogMyra API", version="0.3.5")

# CORS
if CORS_ALLOWED:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOWED,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # Default to permissive if unset (useful for local dev)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# -----------------------------
# Models
# -----------------------------
Role = Literal["user", "assistant", "system"]


class Message(BaseModel):
    role: Role
    content: str


class ChatRequest(BaseModel):
    session_id: str
    messages: List[Message]


class ChatResponse(BaseModel):
    reply: str


class LogRow(BaseModel):
    id: int
    session_id: str
    role: Role
    created_at: datetime
    content: str


# -----------------------------
# Simple in-memory log store
# -----------------------------
_LOG: list[LogRow] = []
_NEXT_ID = 1


def _append_log(session_id: str, role: Role, content: str) -> None:
    global _NEXT_ID
    _LOG.append(
        LogRow(
            id=_NEXT_ID,
            session_id=session_id,
            role=role,
            created_at=datetime.utcnow(),
            content=content,
        )
    )
    _NEXT_ID += 1


def _require_admin(x_admin_key: Optional[str]) -> None:
    if not x_admin_key or x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


# -----------------------------
# Routes
# -----------------------------
@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/diag")
def diag() -> dict:
    return {
        "has_openai_key": bool(OPENAI_API_KEY),
        "origins": CORS_ALLOWED or ["*"],
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """OpenAI-backed chat; logs both user prompt and assistant reply."""
    _append_log(
        req.session_id, "user", req.messages[-1].content if req.messages else ""
    )

    # If no key, fail clearly (prevents silent echo responses)
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=500, detail="OPENAI_API_KEY is not configured on the server."
        )

    client = OpenAI(api_key=OPENAI_API_KEY)

    try:
        # Map incoming messages directly; ensure there is at least one system primer
        messages_payload = (
            [{"role": "system", "content": "You are a concise, helpful assistant."}]
            + [m.model_dump() for m in req.messages]
            if req.messages and req.messages[0].role != "system"
            else [m.model_dump() for m in req.messages]
        )

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages_payload,
            temperature=0.7,
            max_tokens=200,
        )
        reply = resp.choices[0].message.content or "…"
    except Exception as e:
        # Surface model errors, but keep API shape stable
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e!s}") from e

    _append_log(req.session_id, "assistant", reply)
    return ChatResponse(reply=reply)


@app.get("/api/admin/stats")
def admin_stats(
    x_admin_key: Optional[str] = Header(default=None, convert_underscores=False),
) -> dict:
    """Simple counters for sanity checks."""
    _require_admin(x_admin_key)
    total_rows = len(_LOG)
    sessions = sorted({row.session_id for row in _LOG})
    last_entry_at = _LOG[-1].created_at.isoformat() if _LOG else None
    return {
        "total_rows": total_rows,
        "unique_sessions": len(sessions),
        "last_entry_at": last_entry_at,
    }


@app.get("/api/admin/logs")
def admin_logs(
    x_admin_key: Optional[str] = Header(default=None, convert_underscores=False),
) -> JSONResponse:
    """Return the full log as JSON list of rows."""
    _require_admin(x_admin_key)
    return JSONResponse([row.model_dump() for row in _LOG])


@app.get("/api/admin/export.csv")
def admin_export_csv(
    x_admin_key: Optional[str] = Header(default=None, convert_underscores=False),
) -> StreamingResponse:
    """Stream the log as CSV; safe for large outputs."""
    _require_admin(x_admin_key)

    def _gen():
        # header
        yield "id,session_id,role,created_at,content\n"
        # rows
        for r in _LOG:
            buf = StringIO()
            writer = csv.writer(buf)
            writer.writerow(
                [r.id, r.session_id, r.role, r.created_at.isoformat(), r.content]
            )
            yield buf.getvalue()

    headers = {"Content-Disposition": 'attachment; filename="logs.csv"'}
    return StreamingResponse(
        _gen(), media_type="text/csv; charset=utf-8", headers=headers
    )
