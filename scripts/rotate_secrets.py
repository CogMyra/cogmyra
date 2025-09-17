from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path


def set_kv(path: Path, key: str, value: str) -> None:
    """Set or replace KEY=VALUE in a .env-style file, preserving a trailing newline."""
    text = path.read_text() if path.exists() else ""
    lines = [ln for ln in text.splitlines() if not ln.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    out = "\n".join(lines)
    if not out.endswith("\n"):
        out += "\n"
    path.write_text(out)


def main() -> None:
    """Example rotation for local dev. Adjust keys/paths as needed."""
    api_env = Path.home() / "cogmyra-dev" / ".env.local"
    web_env = Path.home() / "cogmyra-dev9" / ".env.local"

    # Generate new secrets
    new_admin = secrets.token_urlsafe(16)
    new_beta = secrets.token_urlsafe(16)

    # Write (create files if missing)
    set_kv(api_env, "ADMIN_PASSWORD", new_admin)
    set_kv(web_env, "VITE_BETA_PASSWORD", new_beta)

    # Write a minimal report without the secrets themselves
    report = Path.home() / "Desktop" / f"CogMyra_Secrets_{datetime.now():%Y-%m-%d}.txt"
    report.write_text(
        "Secrets rotated locally.\n"
        f"- {api_env}\n"
        f"- {web_env}\n"
        "Values are intentionally NOT included in this report.\n"
    )


if __name__ == "__main__":
    main()
