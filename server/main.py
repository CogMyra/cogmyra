# ~/cogmyra-dev/server/main.py
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

VERSION = "api-usage-latency-v3"

app = FastAPI()

WEB_ORIGIN = os.getenv("WEB_ORIGIN", "https://cogmyra-web.onrender.com")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[WEB_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    sessionId: str
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = None


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def _openai_headers() -> Dict[str, str]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }


# Keep the old health if something else uses it, *and* add a new unambiguous one
@app.get("/api/health")
async def health_old() -> Dict[str, str]:
    return {"ok": "true", "version": VERSION}


@app.get("/api/healthz")
async def health_new() -> Dict[str, str]:
    return {"ok": "true", "version": VERSION}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> Dict[str, Any]:
    if not OPENAI_API_KEY:
        return {
            "error": "OPENAI_API_KEY not set",
            "latency_ms": None,
            "usage": None,
            "version": VERSION,
        }

    payload: Dict[str, Any] = {
        "model": req.model,
        "messages": [m.model_dump() for m in req.messages],
    }
    if req.temperature is not None:
        payload["temperature"] = req.temperature

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=_openai_headers(),
                json=payload,
            )
        latency_ms = int((time.perf_counter() - t0) * 1000)
    except Exception as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "session": req.sessionId,
            "model": req.model,
            "reply": "",
            "temperature": req.temperature,
            "usage": None,
            "latency_ms": latency_ms,
            "error": True,
            "status": "network_error",
            "detail": str(e),
            "version": VERSION,
        }

    if r.status_code != 200:
        return {
            "session": req.sessionId,
            "model": req.model,
            "reply": "",
            "temperature": req.temperature,
            "usage": None,
            "latency_ms": latency_ms,
            "error": True,
            "status": r.status_code,
            "data": r.text,
            "version": VERSION,
        }

    data = r.json()
    reply = ""
    try:
        reply = data["choices"][0]["message"]["content"] or ""
    except Exception:
        pass

    usage = data.get("usage") or data.get("x_gpt_usage")

    return {
        "session": req.sessionId,
        "model": req.model,
        "reply": reply,
        "temperature": req.temperature,
        "usage": usage,
        "latency_ms": latency_ms,
        "version": VERSION,
    }
