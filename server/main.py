from typing import List, Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import os
import httpx
import datetime

# -------------------------------------------------
# FastAPI app
# -------------------------------------------------
app = FastAPI()

# ---- CORS (prod + Vite localhost 5170–5199) ----
ALLOWED_ORIGINS = [
    "https://cogmyra-web-app.onrender.com",  # production frontend (old hostname)
    "https://cogmyra-web.onrender.com",  # production frontend (current hostname)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # allow all vite dev ports 5170–5199 on localhost
    allow_origin_regex=r"^http://localhost:5(17|18|19)\d$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------


# -------------------------------------------------
# Models
# -------------------------------------------------
class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    sessionId: str
    messages: List[Message]
    model: Optional[str] = None


# -------------------------------------------------
# Routes
# -------------------------------------------------
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "cogmyra-api",
        "ts": datetime.datetime.utcnow().isoformat(),
        "build": os.getenv("BUILD_TAG", "dev"),
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Proxy chat endpoint → forwards to OpenAI API.
    """
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        return {"error": "OPENAI_API_KEY not set"}

    payload = {
        "model": req.model or "gpt-4.1",
        "messages": [m.dict() for m in req.messages],
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {openai_api_key}"},
            json=payload,
        )
        r.raise_for_status()
        data = r.json()

    return {
        "session": req.sessionId,
        "model": payload["model"],
        "reply": data["choices"][0]["message"]["content"],
    }


# -------------------------------------------------
# Run local dev
# -------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)
