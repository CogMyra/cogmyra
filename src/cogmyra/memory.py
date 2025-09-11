"""Typed in-memory store for user memories.

This module provides a small, typed, in-memory store suitable for capturing
short-lived conversational memory per user. It is intentionally simple and
does not persist across process restarts.
"""

from __future__ import annotations

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

    def __init__(self) -> None:
        """Initialize the store with an empty list of entries."""

        self._entries: List[MemoryEntry] = []

    def add(self, user_id: str, text: str, metadata: dict[str, Any] | None = None) -> MemoryEntry:
        """Add a new memory entry to the store.

        Args:
            user_id: The user identifier to associate with the entry.
            text: The memory text to store.
            metadata: Optional metadata for the entry.

        Returns:
            The created :class:`MemoryEntry` instance.
        """

        entry = MemoryEntry(timestamp=time.time(), user_id=user_id, text=text, metadata=metadata)
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

        filtered = [e for e in self._entries if user_id is None or e.user_id == user_id]
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
        candidates = [e for e in self._entries if user_id is None or e.user_id == user_id]
        matches = [e for e in candidates if needle in e.text.casefold()]
        return list(reversed(matches))
