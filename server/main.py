# ~/cogmyra-dev/server/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

ALLOWED_ORIGINS = [
    # deployed web
    "https://cogmyra-web.onrender.com",
    # local dev (both 5173 and 5174; localhost and 127.0.0.1)
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- rest of your file below (health/healthz/chat endpoints) ---
# keep your existing /api/health, /api/healthz and /api/chat implementations
