from __future__ import annotations

import re
import time

from cogmyra import make_session_id


def test_make_session_id_format_and_length() -> None:
    user_id = "user123"
    sid = make_session_id(user_id)

    assert sid, "session id should not be empty"
    assert len(sid) <= 16
    assert re.fullmatch(r"[A-Za-z0-9_-]+", sid) is not None


def test_make_session_id_changes_over_time() -> None:
    user_id = "sameuser"
    sid1 = make_session_id(user_id)
    time.sleep(1)
    sid2 = make_session_id(user_id)

    assert sid1 != sid2


def test_make_session_id_differs_for_diff_users_same_time(monkeypatch) -> None:
    fixed = 1_700_000_000
    monkeypatch.setattr("cogmyra.core.time", "time", lambda: fixed)

    a = make_session_id("alice")
    b = make_session_id("bob")

    assert a != b
