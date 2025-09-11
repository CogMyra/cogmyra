"""Command-line interface for CogMyra using Typer.

Provides a simple greeting command and a small memory utility group that can
work purely in-memory or persist to a JSONL file when a path is provided.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .core import greet as greet_func
from .memory import MemoryStore

app = typer.Typer(help="CogMyra command-line interface")
mem_app = typer.Typer(help="Memory utilities (in-memory or JSONL-backed)")
app.add_typer(mem_app, name="mem")


@app.command("greet")
def greet(name: str) -> None:
    """Print a friendly greeting for NAME."""

    typer.echo(greet_func(name))


def _store_from_file(file: Optional[Path]) -> MemoryStore:
    return MemoryStore(str(file)) if file is not None else MemoryStore()


@mem_app.command("add")
def mem_add(
    text: str = typer.Argument(..., help="Text of the memory entry"),
    user: str = typer.Option(..., "--user", help="User id for the entry"),
    file: Optional[Path] = typer.Option(
        None, "--file", dir_okay=True, writable=True, help="Optional JSONL file path"
    ),
) -> None:
    """Append a memory entry. Optionally persist to JSONL when FILE is provided."""

    store = _store_from_file(file)
    with store:
        store.add(user_id=user, text=text)
    # Intentionally minimal output; tests rely on subsequent reads.
    typer.echo("OK")


@mem_app.command("last")
def mem_last(
    user: Optional[str] = typer.Option(None, "--user", help="Filter by user id"),
    n: int = typer.Option(5, "--n", min=1, help="Number of entries to show"),
    file: Optional[Path] = typer.Option(None, "--file", help="Optional JSONL file path"),
) -> None:
    """Show the last N entries (most recent first)."""

    store = _store_from_file(file)
    entries = store.get_last(n=n, user_id=user)
    for e in entries:
        # Show ts,user,text as requested
        typer.echo(f"{int(e.timestamp)}\t{e.user_id}\t{e.text}")


@mem_app.command("search")
def mem_search(
    query: str = typer.Argument(..., help="Substring to search for (case-insensitive)"),
    user: Optional[str] = typer.Option(None, "--user", help="Filter by user id"),
    file: Optional[Path] = typer.Option(None, "--file", help="Optional JSONL file path"),
) -> None:
    """Search entries for QUERY and print matches (most recent first)."""

    store = _store_from_file(file)
    matches = store.search(query=query, user_id=user)
    for e in matches:
        typer.echo(f"{int(e.timestamp)}\t{e.user_id}\t{e.text}")
