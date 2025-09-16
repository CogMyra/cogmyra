import datetime
import os
from typing import List, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine, or_
from sqlalchemy.orm import declarative_base, sessionmaker

# Load .env.local (created earlier)
load_dotenv(".env.local")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY in .env.local")

# Database setup
DATABASE_URL = "sqlite:///./interactions.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Interaction(Base):
    __tablename__ = "interactions"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)
    role = Column(String)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    latency_ms = Column(Integer, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    model = Column(String, nullable=True)


Base.metadata.create_all(bind=engine)

# FastAPI app
app = FastAPI(title="CogMyra API")

# CORS – allow only local Vite ports
origins = [
    "http://localhost:5176",
    "http://localhost:5177",
    "http://localhost:5181",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme123")


# Models
class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    session_id: str
    messages: List[Message]


# Auth helper
def require_admin(x_admin_key: str = Header(...)):
    if x_admin_key != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")


# Routes
@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/chat")
def chat(req: ChatRequest):
    import time

    t0 = time.time()
    db = SessionLocal()
    try:
        for m in req.messages:
            db.add(
                Interaction(
                    session_id=req.session_id,
                    role=m.role,
                    content=m.content,
                )
            )
        db.commit()

        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[m.dict() for m in req.messages],
        )
        reply = resp.choices[0].message.content

        latency_ms = int((time.time() - t0) * 1000)
        usage = getattr(resp, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)

        db.add(
            Interaction(
                session_id=req.session_id,
                role="assistant",
                content=reply,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model=getattr(resp, "model", None),
            )
        )
        db.commit()
        return {"reply": reply}
    finally:
        db.close()


@app.get("/api/admin/stats", dependencies=[Depends(require_admin)])
def admin_stats():
    db = SessionLocal()
    try:
        total = db.query(Interaction).count()
        unique_sessions = db.query(Interaction.session_id).distinct().count()
        last = db.query(Interaction.created_at).order_by(Interaction.created_at.desc()).first()
        return {
            "total_rows": total,
            "unique_sessions": unique_sessions,
            "last_entry_at": str(last[0]) if last else None,
        }
    finally:
        db.close()


@app.get("/api/admin/interactions", dependencies=[Depends(require_admin)])
def admin_interactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str = None,
):
    db = SessionLocal()
    try:
        query = db.query(Interaction)
        if q:
            like = f"%{q}%"
            query = query.filter(
                or_(Interaction.content.like(like), Interaction.session_id.like(like))
            )
        total = query.count()
        rows = (
            query.order_by(Interaction.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": r.id,
                    "session_id": r.session_id,
                    "role": r.role,
                    "content": r.content,
                    "created_at": r.created_at,
                    "latency_ms": r.latency_ms,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "model": r.model,
                }
                for r in rows
            ],
        }
    finally:
        db.close()


@app.get("/api/admin/export.csv", dependencies=[Depends(require_admin)])
def admin_export_csv(limit: int = Query(1000, ge=1, le=10000)):
    db = SessionLocal()
    try:
        rows = db.query(Interaction).order_by(Interaction.id.asc()).limit(limit).all()
        out = ["id,session_id,role,created_at,content"]
        for r in rows:
            safe = (r.content or "").replace("\\n", " ").replace(",", ";")
            line = f"{r.id},{r.session_id},{r.role},{r.created_at},{safe}"
            out.append(line)
        text = "\n".join(out)
        return PlainTextResponse(text, media_type="text/csv")
    finally:
        db.close()
