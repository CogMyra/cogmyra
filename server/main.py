# server/main.py
from __future__ import annotations

import json
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List

import uvicorn
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# --- Optional OpenAI (graceful if not installed / no key) --------------------
OPENAI_AVAILABLE = False
try:
    # New-style OpenAI SDK (2024+)
    from openai import OpenAI  # type: ignore

    OPENAI_AVAILABLE = True
except Exception:  # pragma: no cover
    OPENAI_AVAILABLE = False


# -----------------------------------------------------------------------------
# App + CORS
# -----------------------------------------------------------------------------
app = FastAPI(title="CogMyra API")

ALLOWED_ORIGINS = [
    # hosted web
    "https://cogmyra-web.onrender.com",
    # local dev (vite)
    "http://localhost:5175",
    "http://127.0.0.1:5175",
    # local API (when UI calls 127.0.0.1:8000 directly)
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# Persistent logs (JSONL) + in-memory ring buffer
# -----------------------------------------------------------------------------
LOGS_FILE = Path(
    os.getenv("LOGS_FILE", str(Path(__file__).parent / "logs" / "events.jsonl"))
)
LOGS_FILE.parent.mkdir(parents=True, exist_ok=True)

LOGS: Deque[Dict[str, Any]] = deque(maxlen=500)


def _append_jsonl(obj: Dict[str, Any]) -> None:
    try:
        with LOGS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception:
        # Logging should never crash the app
        pass


def log(kind: str, msg: str, **extra: Any) -> None:
    entry: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": kind,
        "msg": msg,
        **extra,
    }
    LOGS.appendleft(entry)
    _append_jsonl(entry)


# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------
@app.get("/api/health")
async def api_health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


# -----------------------------------------------------------------------------
# Admin logs (read-only)
#   GET /api/admin/logs?limit=50
# -----------------------------------------------------------------------------
@app.get("/api/admin/logs")
async def api_admin_logs(limit: int = Query(50, ge=1, le=500)) -> JSONResponse:
    entries: List[Dict[str, Any]] = []

    # Try to tail the JSONL on disk (up to ~1MB from the end)
    try:
        if LOGS_FILE.exists():
            chunk = LOGS_FILE.read_bytes()[-1_048_576:]  # 1 MB window
            lines = chunk.splitlines()
            for line in reversed(lines):
                try:
                    entries.append(json.loads(line.decode("utf-8")))
                    if len(entries) >= limit:
                        break
                except Exception:
                    continue
            entries.reverse()
    except Exception:
        # Ignore file errors; we'll still serve in-memory logs
        pass

    # If we still need more, top up from memory (newest-first)
    if len(entries) < limit:
        mem = list(LOGS)[: (limit - len(entries))]
        entries = mem + entries

    return JSONResponse({"entries": entries})


# -----------------------------------------------------------------------------
# Chat
#   POST /api/chat
#   Body:
#     {
#       "messages": [{ "role": "system"|"user"|"assistant", "content": "..." }, ...],
#       "sessionId": "local-dev" (optional)
#     }
# -----------------------------------------------------------------------------
DEFAULT_SYSTEM = "You are CogMyra Guide (CMG). Be concise, helpful, and transparent."


def _pick_user_prompt(messages: List[Dict[str, Any]]) -> str:
    """
    Used only for echo fallback and logging: returns most-recent user string.
    """
    if not isinstance(messages, list):
        return ""
    # newest user first
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c
    # fallback: any latest string-ish content
    for m in reversed(messages):
        if isinstance(m, dict):
            c = m.get("content")
            if isinstance(c, str):
                return c
    return ""


def _openai_enabled() -> bool:
    """
    Use OpenAI only if library is importable AND key is present.
    """
    if not OPENAI_AVAILABLE:
        return False
    return bool(os.getenv("OPENAI_API_KEY"))


@app.post("/api/chat")
async def api_chat(
    payload: Dict[str, Any] = Body(...),
    request: Request = None,  # noqa: ARG001
) -> JSONResponse:
    messages = payload.get("messages", [])
    session_id = payload.get("sessionId", "unknown")

    prompt = _pick_user_prompt(messages)
    log("chat_req", "received prompt", prompt=prompt, session=session_id)

    # Friendly error on empty prompt
    if not prompt:
        log("chat_res", "missing prompt", reply="Echo: None", session=session_id)
        raise HTTPException(status_code=400, detail="No prompt provided")

    # Try OpenAI first if available, else echo fallback
    if _openai_enabled():
        try:
            client = OpenAI()  # key from env
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

            # Use caller-supplied message array; inject default system if none
            final_msgs: List[Dict[str, str]] = []
            has_system = any(
                isinstance(m, dict) and m.get("role") == "system" for m in messages
            )
            if not has_system:
                final_msgs.append({"role": "system", "content": DEFAULT_SYSTEM})

            for m in messages:
                if isinstance(m, dict):
                    role = m.get("role")
                    content = m.get("content")
                    if role in {"system", "user", "assistant"} and isinstance(
                        content, str
                    ):
                        final_msgs.append({"role": role, "content": content})

            resp = client.chat.completions.create(
                model=model,
                messages=final_msgs,
                temperature=0.2,
                max_tokens=512,
            )
            reply = (resp.choices[0].message.content or "").strip()
            if not reply:
                reply = "Sorry — I couldn't produce a reply."

            log(
                "chat_res",
                "sending reply",
                reply=reply,
                session=session_id,
                provider="openai",
                model=model,
            )
            return JSONResponse({"reply": reply})
        except Exception as e:
            # Graceful fallback
            log("chat_err", "openai error", error=str(e))

    # Echo fallback
    reply = f"Echo: {prompt}"
    log("chat_res", "sending reply", reply=reply, session=session_id, provider="echo")
    return JSONResponse({"reply": reply})


# -----------------------------------------------------------------------------
# Local dev entry (optional)
# -----------------------------------------------------------------------------
if __name__ == "__main__":  # pragma: no cover
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("server.main:app", host="0.0.0.0", port=port, reload=True)
