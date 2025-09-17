import datetime
import os
from typing import List, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# -----------------------------------------------------------------------------
# Env & config
# -----------------------------------------------------------------------------
load_dotenv(".env.local")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY in .env.local")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme123")

DB_PATH = os.getenv(
    "DB_PATH", os.path.join(os.path.dirname(__file__), "..", "interactions.db")
)
DB_PATH = os.path.abspath(DB_PATH)

# -----------------------------------------------------------------------------
# DB setup
# -----------------------------------------------------------------------------
engine = create_engine(
    f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Interaction(Base):
    __tablename__ = "interactions"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), index=True)
    role = Column(String(16))  # "user" | "assistant" | "system"
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    # optional metrics
    latency_ms = Column(Integer, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    model = Column(String(64), nullable=True)


Base.metadata.create_all(bind=engine)


def _ensure_columns() -> None:
    with engine.connect() as conn:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(interactions);")}

        def add(col: str, ddl: str) -> None:
            if col not in cols:
                conn.exec_driver_sql(f"ALTER TABLE interactions ADD COLUMN {ddl}")

        add("latency_ms", "latency_ms INTEGER")
        add("prompt_tokens", "prompt_tokens INTEGER")
        add("completion_tokens", "completion_tokens INTEGER")
        add("model", "model VARCHAR(64)")


_ensure_columns()

# -----------------------------------------------------------------------------
# FastAPI app & CORS
# -----------------------------------------------------------------------------
app = FastAPI(title="CogMyra Local API")

# Allow only your local Vite ports (add/remove as needed)
origins = [
    "http://localhost:5175",
    "http://localhost:5176",
    "http://localhost:5177",
    "http://localhost:5181",
    "http://localhost:5185",
]


# CORS – allow only configured origins
_env_origins = os.getenv(
    "CORS_ORIGINS"
)  # e.g. "http://localhost:5185,https://app.yourdomain.com"
origins = (
    [o.strip() for o in _env_origins.split(",")]
    if _env_origins
    else [
        "http://localhost:5176",
        "http://localhost:5177",
        "http://localhost:5181",
        "http://localhost:5185",
    ]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# OpenAI client
# -----------------------------------------------------------------------------
client = OpenAI(api_key=OPENAI_API_KEY)


# -----------------------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------------------
class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    session_id: str = Field(..., max_length=64)
    messages: List[Message]


class ChatResponse(BaseModel):
    reply: str


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def log_interaction(db, session_id: str, role: str, content: str) -> None:
    db.add(Interaction(session_id=session_id, role=role, content=content))
    db.commit()


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/chat", response_model=ChatResponse)
def chat(body: ChatRequest):
    db = SessionLocal()
    try:
        # log user message
        for m in body.messages:
            if m.role == "user":
                log_interaction(db, body.session_id, "user", m.content)

        # call OpenAI and time it
        import time

        t0 = time.time()
        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=[{"role": m.role, "content": m.content} for m in body.messages],
        )
        reply = resp.output_text
        latency_ms = int((time.time() - t0) * 1000)

        usage = getattr(resp, "usage", None)
        prompt_tokens = getattr(usage, "input_tokens", None) or getattr(
            usage, "prompt_tokens", None
        )
        completion_tokens = getattr(usage, "output_tokens", None) or getattr(
            usage, "completion_tokens", None
        )
        model_name = getattr(resp, "model", None) or "gpt-4.1-mini"

        # log assistant reply with metrics
        db.add(
            Interaction(
                session_id=body.session_id,
                role="assistant",
                content=reply,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model=model_name,
            )
        )
        db.commit()

        return {"reply": reply}
    finally:
        db.close()


# -----------------------------------------------------------------------------
# Admin guard & endpoints
# -----------------------------------------------------------------------------
def require_admin(x_admin_key: str = Header(None)):
    if not x_admin_key or x_admin_key != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


@app.get("/api/admin/stats", dependencies=[Depends(require_admin)])
def admin_stats():
    db = SessionLocal()
    try:
        total = db.query(Interaction).count()
        users = db.query(Interaction.session_id).distinct().count()
        last = db.query(Interaction).order_by(Interaction.id.desc()).first()
        return {
            "total_rows": total,
            "unique_sessions": users,
            "last_entry_at": getattr(last, "created_at", None),
        }
    finally:
        db.close()


@app.get("/api/admin/interactions", dependencies=[Depends(require_admin)])
def admin_interactions(
    q: str | None = Query(default=None, description="substring search"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    db = SessionLocal()
    try:
        query = db.query(Interaction)
        if q:
            like = f"%{q}%"
            from sqlalchemy import or_

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
            safe = (r.content or "").replace("\n", " ").replace(",", ";")
            line = f"{r.id},{r.session_id},{r.role},{r.created_at},{safe}"
            out.append(line)
        text = "\n".join(out)
        return PlainTextResponse(text, media_type="text/csv")
    finally:
        db.close()
