# server/main.py
from __future__ import annotations

import csv
import hashlib
import io
import os
from typing import Iterable

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, Request

app = FastAPI(title="CogMyra API")

# === Admin key handling =======================================================
# Read once at process start. On Render, set either ADMIN_KEY or COGMYRA_ADMIN_KEY.
_ADMIN_KEY_RAW = os.getenv("ADMIN_KEY") or os.getenv("COGMYRA_ADMIN_KEY") or ""


def _extract_admin_key(
    request: Request, authorization: str | None, x_admin_key: str | None
) -> str | None:
    """
    Accept either:
      - Header: x-admin-key: <key>
      - Header: Authorization: Bearer <key>
    """
    if x_admin_key:
        return x_admin_key.strip()
    if authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
    return None


async def require_admin(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_admin_key: str | None = Header(default=None, alias="x-admin-key"),
) -> None:
    if not _ADMIN_KEY_RAW:
        # Misconfigured server env
        raise HTTPException(status_code=500, detail="Admin key not configured")
    supplied = _extract_admin_key(request, authorization, x_admin_key)
    if not supplied or supplied != _ADMIN_KEY_RAW:
        raise HTTPException(status_code=401, detail="Unauthorized")


# === Health ===================================================================
@app.get("/api/health")
async def health():
    return {"ok": True}


# === CSV export ==============================================================#
def _iter_logs(limit: int) -> Iterable[dict]:
    """
    Replace this stub with your real DB query.
    Keep the keys matching the CSV header below.
    """
    sample = [
        {
            "id": 1,
            "session_id": "smoke",
            "role": "user",
            "created_at": "2025-09-20T23:26:10.175188",
            "content": "Say hi in 6 words.",
        },
        {
            "id": 2,
            "session_id": "smoke",
            "role": "assistant",
            "created_at": "2025-09-20T23:26:11.257233",
            "content": "Hello! How can I assist you today?",
        },
    ]
    yield from sample[:limit]


@app.get("/api/admin/export.csv", dependencies=[Depends(require_admin)])
async def admin_export_csv(limit: int = Query(1000, ge=1, le=10000)) -> Response:
    """
    Return logs as CSV. Swap _iter_logs() with your real query.
    """
    buf = io.StringIO()
    fieldnames = ["id", "session_id", "role", "created_at", "content"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in _iter_logs(limit):
        writer.writerow(row)
    csv_bytes = buf.getvalue().encode("utf-8")
    return Response(content=csv_bytes, media_type="text/csv")


# === Debug: compare admin key hash (enable only when DEBUG_ADMIN=1) ===========
@app.get("/api/_debug/admin-key-hash")
async def _debug_admin_key_hash():
    if os.getenv("DEBUG_ADMIN") != "1":
        raise HTTPException(status_code=404, detail="Not Found")
    h = hashlib.sha256(_ADMIN_KEY_RAW.encode()).hexdigest() if _ADMIN_KEY_RAW else None
    return {"server_hash": h, "key_len": len(_ADMIN_KEY_RAW) if _ADMIN_KEY_RAW else 0}
