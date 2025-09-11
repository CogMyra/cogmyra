"""Core functionality for CogMyra."""

from __future__ import annotations

import base64
import hashlib
import time


def greet(name: str) -> str:
    """Return a friendly greeting for the given name."""

    return f"Hello, {name}!"


def make_session_id(user_id: str) -> str:
    """Return a short, URL-safe session id derived from ``user_id`` and current time.

    The ID is derived as follows:
    - Compute a SHA-256 digest of the string ``f"{user_id}:{int(time.time())}"``
    - Base64 URL-safe encode the digest and strip any trailing ``=`` padding
    - Return the first 16 characters for brevity
    """

    payload = f"{user_id}:{int(time.time())}".encode()
    digest = hashlib.sha256(payload).digest()
    encoded = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return encoded[:16]
