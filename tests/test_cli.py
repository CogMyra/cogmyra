from __future__ import annotations

import os
import subprocess
from pathlib import Path


def run_cli(*args: str, cwd: str | None = None) -> str:
    env = os.environ.copy()
    # Ensure Poetry uses the local virtualenv if present
    cmd = ["poetry", "run", "cogmyra", *args]
    out = subprocess.check_output(cmd, cwd=cwd, text=True, env=env)
    return out.strip()


def test_greet_cli() -> None:
    out = run_cli("greet", "World")
    assert "Hello, World!" in out


def test_mem_roundtrip_cli(tmp_path: Path) -> None:
    file_path = tmp_path / "mem.jsonl"

    # Add two entries to the JSONL-backed store
    run_cli("mem", "add", "hello there", "--user", "alice", "--file", str(file_path))
    run_cli("mem", "add", "general kenobi", "--user", "bob", "--file", str(file_path))

    # last --n 2 should include both entries
    last_out = run_cli("mem", "last", "--n", "2", "--file", str(file_path))
    assert "hello there" in last_out
    assert "general kenobi" in last_out

    # search for a substring
    search_out = run_cli("mem", "search", "hello", "--file", str(file_path))
    assert "hello there" in search_out
