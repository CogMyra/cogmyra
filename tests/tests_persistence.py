from __future__ import annotations

import threading
from typing import Final

from cogmyra import MemoryStore


def test_roundtrip_jsonl(tmp_path) -> None:
    file_path = tmp_path / "mem.jsonl"

    store = MemoryStore(str(file_path))
    a1 = store.add("alice", "one")
    b1 = store.add("bob", "two")
    a2 = store.add("alice", "three")

    store.save()

    # Re-instantiate and ensure entries are loaded and ordered correctly
    store2 = MemoryStore(str(file_path))
    last_all = store2.get_last(3)
    assert [e.text for e in last_all] == [a2.text, b1.text, a1.text]


def test_context_manager_saves(tmp_path) -> None:
    file_path = tmp_path / "mem.jsonl"

    with MemoryStore(str(file_path)) as store:
        store.add("u", "first")
        store.add("u", "second")

    store2 = MemoryStore(str(file_path))
    last = store2.get_last(10)
    assert [e.text for e in last] == ["second", "first"]


def test_thread_safety_basic(tmp_path) -> None:
    file_path = tmp_path / "mem.jsonl"
    store = MemoryStore(str(file_path))

    COUNT: Final[int] = 50

    def add_batch(user: str) -> None:
        for i in range(COUNT):
            store.add(user, f"hello {i}")

    t1 = threading.Thread(target=add_batch, args=("u1",))
    t2 = threading.Thread(target=add_batch, args=("u2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    store.save()

    # Reload and verify total count and ability to search
    store2 = MemoryStore(str(file_path))
    all_last = store2.get_last(1000)
    assert len(all_last) == COUNT * 2

    search_results = store2.search("hello 0")
    # Expect two matches: from u1 and u2
    assert 1 <= len(search_results) <= 2
    assert all("hello 0" in e.text for e in search_results)
