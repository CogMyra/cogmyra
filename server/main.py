# === BEGIN ADMIN AUTH BLOCK (paste once) ======================================
import os
import hmac
from typing import Optional

from fastapi import Header, HTTPException, Request, status

# Read the admin key from env (support both names), strip whitespace/newlines
_ADMIN_KEY_RAW: str = (
    os.getenv("ADMIN_KEY") or os.getenv("COGMYRA_ADMIN_KEY") or ""
).strip()


def _extract_admin_token(
    request: Request, authorization: Optional[str]
) -> Optional[str]:
    """
    Pull admin token from either:
      - 'x-admin-key' header
      - 'Authorization: Bearer <token>' header
    Returns the token or None.
    """
    # Case-insensitive access via Starlette's Headers
    x_admin = request.headers.get("x-admin-key")
    if x_admin:
        return x_admin.strip()

    if authorization:
        # Accept "Bearer <token>" (case-insensitive for 'Bearer')
        parts = authorization.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()

    return None


def require_admin(
    request: Request,
    authorization: Optional[str] = Header(default=None, convert_underscores=False),
) -> None:
    """
    FastAPI dependency: raises 401 unless a valid admin token is provided.
    """
    if not _ADMIN_KEY_RAW:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin key not configured on server",
        )

    provided = _extract_admin_token(request, authorization)
    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing admin credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Constant-time compare
    if not hmac.compare_digest(provided, _ADMIN_KEY_RAW):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )


# === END ADMIN AUTH BLOCK =====================================================
