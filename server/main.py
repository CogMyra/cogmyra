# server/main.py
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from fastapi import Body, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
app = FastAPI(title="CogMyra API")

# -----------------------------------------------------------------------------
# CORS
#   - Deployed web app on Render
#   - Local dev (localhost or 127.0.0.1 on any port)
# -----------------------------------------------------------------------------
ALLOWED_ORIGINS = ["https://cogmyra-web.onrender.com"]
LOCALHOST_REGEX = r"^https?://(?:localhost|127\.0\.0\.1)(?::\d+)?$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=LOCALHOST_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Simple in-memory logging
# -----------------------------------------------------------------------------
MAX_LOGS = 500
LOGS: Deque[Dict[str, Any]] = deque(maxlen=MAX_LOGS)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(kind: str, msg: str, extra: Optional[Dict[str, Any]] = None) -> None:
    entry = {"ts": now_iso(), "kind": kind, "msg": msg}
    if extra:
        entry.update(extra)
    LOGS.append(entry)


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/api/health")
async def health() -> Dict[str, bool]:
    return {"ok": True}


@app.post("/api/chat")
async def chat(payload: Dict[str, Any] = Body(...)) -> Dict[str, str]:
    """
    Echo-style endpoint the frontend is already calling.
    """
    prompt = (payload or {}).get("prompt")
    log("chat_req", "received prompt", {"prompt": prompt})
    reply = f"Echo: {prompt}" if prompt is not None else "Echo: None"
    log("chat_res", "sending reply", {"reply": reply})
    return {"reply": reply}


@app.get("/api/admin/logs")
async def admin_logs(limit: int = Query(20, ge=1, le=200)) -> List[Dict[str, Any]]:
    """
    Return the most recent log entries (up to `limit`).
    """
    items = list(LOGS)[-limit:]
    return items


# Optional: catch-all error handler to log unexpected errors nicely
@app.exception_handler(Exception)
async def on_unhandled_error(request: Request, exc: Exception):
    log(
        "error",
        "unhandled exception",
        {"path": request.url.path, "detail": str(exc)},
    )
    return JSONResponse(status_code=500, content={"error": "internal_error"})
