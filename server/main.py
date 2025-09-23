from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime

app = FastAPI()

# ---------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can tighten this later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------
LOGS = []


def log(kind: str, msg: str, **extra):
    entry = {"ts": datetime.utcnow().isoformat(), "kind": kind, "msg": msg}
    entry.update(extra)
    LOGS.append(entry)
    if len(LOGS) > 200:
        LOGS.pop(0)
    print("LOG:", entry)


@app.get("/api/admin/logs")
async def api_logs() -> JSONResponse:
    return JSONResponse({"entries": list(LOGS)})


# ---------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------
@app.post("/api/chat")
async def api_chat(request: Request) -> JSONResponse:
    try:
        data = await request.json()
    except Exception:
        data = {}

    # Expecting OpenAI-style { messages: [{role, content}, ...] }
    messages = data.get("messages", [])
    prompt = None
    if messages and isinstance(messages, list):
        for m in reversed(messages):
            if m.get("role") == "user":
                prompt = m.get("content")
                break

    # Fallback: allow { "prompt": "hello" }
    if not prompt:
        prompt = data.get("prompt")

    log("chat_req", "received prompt", prompt=prompt)

    # Simple echo fallback
    reply = f"Echo: {prompt}" if prompt else "Echo: None"
    log("chat_res", "sending reply", reply=reply)

    return JSONResponse({"reply": reply})


# ---------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------
@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})
