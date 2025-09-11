from __future__ import annotations

from cogmyra import MemoryEntry, MemoryStore


def test_add_returns_entry_and_increases_count() -> None:
    store = MemoryStore()

    assert store.get_last(10) == []

    e1 = store.add("u1", "hello")
    assert isinstance(e1, MemoryEntry)

    after_one = store.get_last(10)
    assert len(after_one) == 1
    assert after_one[0] == e1

    e2 = store.add("u2", "world")
    after_two = store.get_last(10)
    assert len(after_two) == 2
    assert after_two[0] == e2
    assert after_two[1] == e1


def test_get_last_with_and_without_user_filter() -> None:
    store = MemoryStore()
    a1 = store.add("alice", "one")
    b1 = store.add("bob", "two")
    a2 = store.add("alice", "three")

    # Without filter: most recent first across all users
    last_all = store.get_last(3)
    assert last_all == [a2, b1, a1]

    # With user filter: only that user's entries, most recent first
    last_alice = store.get_last(5, user_id="alice")
    assert last_alice == [a2, a1]

    last_bob = store.get_last(5, user_id="bob")
    assert last_bob == [b1]


def test_search_finds_matches_and_respects_user_filter() -> None:
    store = MemoryStore()
    a1 = store.add("alice", "Hello world")
    store.add("alice", "no match here")
    b1 = store.add("bob", "HELLO again")
    store.add("bob", "something else")

    # Case-insensitive search across users, most recent first
    results = store.search("hello")
    assert results[0] == b1
    assert a1 in results
    assert all("hello" in e.text.lower() for e in results)

    # User-filtered search
    alice_results = store.search("hello", user_id="alice")
    assert alice_results == [a1]
