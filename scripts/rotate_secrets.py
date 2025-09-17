#!/usr/bin/env python3
"""
rotate_secrets.py

Tiny helper to (re)write key=value pairs into a .env-style file
without duplicating lines, and always ending with a newline.
"""

from __future__ import annotations

from pathlib import Path


def set_env_kv(path: Path, key: str, value: str) -> None:
    """
    Upsert KEY=VALUE into a .env-like file.
    - Replaces the existing line if KEY=... already exists.
    - Appends a new line otherwise.
    - Ensures the file ends with a trailing newline.
    """
    text = path.read_text() if path.exists() else ""
    lines = text.splitlines()
    found = False

    for i, line in enumerate(lines):
        # ignore comments and blank lines when matching
        if not line or line.lstrip().startswith("#"):
            continue
        if line.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            found = True
            break

    if not found:
        lines.append(f"{key}={value}")

    out = "\n".join(lines)
    if not out.endswith("\n"):
        out += "\n"
    path.write_text(out)


def main() -> None:
    """
    Example usage:
      - Update web .env.local (Vite)
      - Update server .env.local (FastAPI)

    Adjust paths/keys as needed for your workflow, or call set_env_kv
    from another script.
    """
    repo = Path(__file__).resolve().parents[1]
    web_env = repo / "cogmyra-dev9" / ".env.local"
    api_env = repo / ".env.local"

    # No-op examples (uncomment and set values if you want to use this script directly):
    # set_env_kv(web_env, "VITE_BETA_PASSWORD", "REDACTED")
    # set_env_kv(web_env, "VITE_API_BASE", "http://localhost:8001")
    # set_env_kv(api_env, "ADMIN_PASSWORD", "REDACTED")
    # set_env_kv(api_env, "OPENAI_API_KEY", "sk-...")

    # print paths so CI/logs show what we touched
    print(f"OK: script ready. Web env: {web_env}")
    print(f"OK: script ready. API env: {api_env}")


if __name__ == "__main__":
    main()
