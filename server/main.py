# ~/cogmyra-dev/server/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import time
import httpx

app = FastAPI()

# Allowed frontend origins
ALLOWED_ORIGINS = [
    "https://cogmyra-web.onrender.com",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------- Models ---------
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    sessionId: str
    model: str
    messages: list[ChatMessage]
    temperature: float | None = None


# --------- Routes ---------
@app.get("/api/health")
async def health():
    return {
        "ok": "true",
        "version": "api-usage-latency-v3",
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Proxy chat endpoint → forwards to OpenAI API and returns reply,
    plus latency, usage, version.
    """
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        return {"error": "OPENAI_API_KEY not set"}

    headers = {"Authorization": f"Bearer {openai_api_key}"}
    body = {
        "model": req.model,
        "messages": [m.dict() for m in req.messages],
    }
    if req.temperature is not None:
        body["temperature"] = req.temperature

    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=body,
        )
    dt = int((time.perf_counter() - t0) * 1000)

    data = r.json()
    reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")

    return {
        "session": req.sessionId,
        "model": req.model,
        "reply": reply,
        "temperature": req.temperature,
        "latency_ms": dt,
        "usage": data.get("usage"),
        "version": "api-usage-latency-v3",
    }
