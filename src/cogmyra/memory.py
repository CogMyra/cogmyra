"""Typed in-memory store for user memories.

This module provides a small, typed store suitable for capturing conversational
memory per user. It can optionally persist entries to a JSON Lines (JSONL)
file for simple durability across process restarts.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, List


@dataclass
class MemoryEntry:
    """A single memory entry.

    Attributes:
        timestamp: UNIX timestamp (seconds since epoch) when the entry was added.
        user_id: Identifier for the user this entry belongs to.
        text: The textual content of the memory.
        metadata: Optional structured metadata associated with the entry.
    """

    timestamp: float
    user_id: str
    text: str
    metadata: dict[str, Any] | None = None


class MemoryStore:
    """A simple, in-memory store for :class:`MemoryEntry` objects.

    The store keeps entries in insertion order (oldest first). Retrieval methods
    return entries with the most recent first when appropriate.
    """

    def __init__(self, file_path: str | None = None) -> None:
        """Initialize the store.

        Args:
            file_path: Optional path to a JSONL file used for persistence. If provided,
                existing entries from the file are loaded into memory. If the file
                does not exist, it is ignored until the first save.
        """

        self._entries: List[MemoryEntry] = []
        self._file_path: str | None = file_path
        self._lock = threading.Lock()
        # Tracks how many entries have been flushed to disk to support append-only saves.
        self._saved_upto: int = 0

        if self._file_path is not None:
            # Best-effort load; ignore if file missing.
            self.load()

    def add(
        self, user_id: str, text: str, metadata: dict[str, Any] | None = None
    ) -> MemoryEntry:
        """Add a new memory entry to the store.

        Args:
            user_id: The user identifier to associate with the entry.
            text: The memory text to store.
            metadata: Optional metadata for the entry.

        Returns:
            The created :class:`MemoryEntry` instance.
        """

        entry = MemoryEntry(
            timestamp=time.time(), user_id=user_id, text=text, metadata=metadata
        )
        with self._lock:
            self._entries.append(entry)
        return entry

    def get_last(self, n: int = 1, user_id: str | None = None) -> list[MemoryEntry]:
        """Return the last ``n`` entries, most recent first.

        Args:
            n: The maximum number of entries to return.
            user_id: If provided, only entries matching this user are considered.

        Returns:
            A list of up to ``n`` entries ordered from most recent to least recent.
        """

        with self._lock:
            filtered = [
                e for e in self._entries if user_id is None or e.user_id == user_id
            ]
            return list(reversed(filtered))[:n]

    def search(self, query: str, user_id: str | None = None) -> list[MemoryEntry]:
        """Search for entries where ``query`` is a substring of the text.

        The match is case-insensitive. If ``user_id`` is provided, the search is limited
        to that user's entries. Results are returned with most recent first.

        Args:
            query: Substring to look for (case-insensitive).
            user_id: Optional user filter.

        Returns:
            A list of matching entries ordered from most recent to least recent.
        """

        needle = query.casefold()
        with self._lock:
            candidates = [
                e for e in self._entries if user_id is None or e.user_id == user_id
            ]
            matches = [e for e in candidates if needle in e.text.casefold()]
            return list(reversed(matches))

    # Persistence API
    def save(self) -> None:
        """Append any new entries since last save to the JSONL file.

        If no ``file_path`` was provided at initialization, this is a no-op.
        """

        if self._file_path is None:
            return

        with self._lock:
            # Nothing new to write
            if self._saved_upto >= len(self._entries):
                return

            to_write = self._entries[self._saved_upto :]

            # Ensure parent directory exists for the target file if a parent is specified.
            parent = os.path.dirname(self._file_path)
            if parent:
                os.makedirs(parent, exist_ok=True)

            with open(self._file_path, "a", encoding="utf-8") as f:
                for e in to_write:
                    obj = {
                        "timestamp": e.timestamp,
                        "user_id": e.user_id,
                        "text": e.text,
                        "metadata": e.metadata,
                    }
                    f.write(json.dumps(obj, ensure_ascii=False) + "\n")

            self._saved_upto = len(self._entries)

    def load(self) -> None:
        """Load entries from JSONL file into memory; de-duplicate by (timestamp,user_id,text).

        Keeps in-memory order as oldest to newest. If the file does not exist, the
        method returns without error.
        """

        if self._file_path is None:
            return

        if not os.path.exists(self._file_path):
            # Nothing to load
            return

        loaded: list[MemoryEntry] = []
        seen: set[tuple[float, str, str]] = set()

        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        # Skip malformed lines
                        continue

                    try:
                        ts = float(obj["timestamp"])  # type: ignore[assignment]
                        uid = str(obj["user_id"])  # type: ignore[assignment]
                        text = str(obj["text"])  # type: ignore[assignment]
                        metadata = obj.get("metadata")
                        if metadata is not None and not isinstance(metadata, dict):
                            metadata = None
                    except (KeyError, ValueError, TypeError):
                        # Skip if required fields missing or wrong types
                        continue

                    key = (ts, uid, text)
                    if key in seen:
                        continue
                    seen.add(key)
                    loaded.append(
                        MemoryEntry(
                            timestamp=ts, user_id=uid, text=text, metadata=metadata
                        )
                    )
        finally:
            # Replace in one shot under lock to avoid partial reads by other threads
            with self._lock:
                self._entries = loaded
                # Consider everything from disk as already saved
                self._saved_upto = len(self._entries)

    # Context manager support
    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        # Always attempt to save on exit if persistence is enabled.
        self.save()
