# server/main.py
from __future__ import annotations


from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="CogMyra API")

# --- CORS -------------------------------------------------------------
ALLOWED_ORIGINS = [
    "https://cogmyra-web.onrender.com",  # deployed web
    "http://localhost:5173",  # local dev (Vite)
    "http://127.0.0.1:5173",  # local dev (alternate)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Example routes ---------------------------------------------------
@app.get("/api/health")
async def health():
    return {"ok": True}


@app.post("/api/chat")
async def chat(req: Request):
    data = await req.json()
    # For now, just echo back
    return {"reply": f"Echo: {data.get('message')}"}
