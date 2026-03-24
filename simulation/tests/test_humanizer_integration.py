# simulation/tests/test_humanizer_integration.py
# pyright: reportMissingImports=false, reportImplicitRelativeImport=false

import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _create_oasis_db(path: str) -> None:
    """Create a minimal OASIS-schema DB for testing."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE user (
            user_id INTEGER PRIMARY KEY,
            agent_id INTEGER,
            user_name TEXT,
            name TEXT,
            bio TEXT,
            created_at TEXT,
            num_followings INTEGER,
            num_followers INTEGER
        );
        CREATE TABLE post (
            post_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            content TEXT,
            num_likes INTEGER,
            num_dislikes INTEGER,
            created_at TEXT
        );
        CREATE TABLE comment (
            comment_id INTEGER PRIMARY KEY,
            post_id INTEGER,
            user_id INTEGER,
            content TEXT,
            created_at TEXT,
            num_likes INTEGER,
            num_dislikes INTEGER
        );
    """)
    conn.commit()
    conn.close()


@pytest.fixture
def oasis_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    _create_oasis_db(path)
    yield path
    os.unlink(path)


def test_humanize_comments_zero_comments_returns_zero(oasis_db):
    from scripts.run_simulation import humanize_comments

    result = humanize_comments(oasis_db)
    assert result == 0


import json


def _seed_oasis_comments(path: str) -> None:
    """Insert a user and two comments into the OASIS DB."""
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO user (user_id, user_name, name, bio, created_at, num_followings, num_followers) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (1, "skeptic_jordan", "Jordan", "PM", "2026-01-01", 0, 0),
    )
    conn.execute(
        "INSERT INTO post (post_id, user_id, content, num_likes, num_dislikes, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (1, 99, "seed post", 0, 0, "2026-01-01"),
    )
    conn.execute(
        "INSERT INTO comment (comment_id, post_id, user_id, content, created_at, num_likes, num_dislikes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (1, 1, 1, "This is a pivotal testament to the evolving landscape.", "2026-01-01T10:00", 0, 0),
    )
    conn.execute(
        "INSERT INTO comment (comment_id, post_id, user_id, content, created_at, num_likes, num_dislikes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (2, 1, 1, "Additionally, it delves into the intricate interplay.", "2026-01-01T10:05", 0, 0),
    )
    conn.commit()
    conn.close()


def test_humanize_comments_rewrites_content(oasis_db, monkeypatch):
    _seed_oasis_comments(oasis_db)

    fake_response = json.dumps([
        {"id": 1, "content": "This is an important step for regional statistics."},
        {"id": 2, "content": "It also explores how these forces interact."},
    ])

    # Monkeypatch the _ask_humanizer helper — this bypasses ModelFactory,
    # ChatAgent, and BaseMessage entirely, matching the codebase convention
    # (see test_scorecard.py monkeypatching _ask_llm)
    from scripts import run_simulation
    monkeypatch.setattr(run_simulation, "_ask_humanizer", lambda prompt: fake_response)

    calls = run_simulation.humanize_comments(oasis_db)
    assert calls == 1

    # Verify DB was updated
    conn = sqlite3.connect(oasis_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT comment_id, content FROM comment ORDER BY comment_id").fetchall()
    conn.close()

    assert rows[0]["content"] == "This is an important step for regional statistics."
    assert rows[1]["content"] == "It also explores how these forces interact."


def test_humanize_comments_handles_llm_failure(oasis_db, monkeypatch):
    _seed_oasis_comments(oasis_db)

    def _fake_ask_humanizer(prompt):
        raise RuntimeError("LLM API timeout")

    from scripts import run_simulation
    monkeypatch.setattr(run_simulation, "_ask_humanizer", _fake_ask_humanizer)

    calls = run_simulation.humanize_comments(oasis_db)
    assert calls == 0  # no successful calls

    # Verify DB is unchanged
    conn = sqlite3.connect(oasis_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT comment_id, content FROM comment ORDER BY comment_id").fetchall()
    conn.close()

    assert "pivotal testament" in rows[0]["content"]  # original preserved
    assert "delves into" in rows[1]["content"]  # original preserved


def test_humanize_comments_handles_bad_json(oasis_db, monkeypatch):
    _seed_oasis_comments(oasis_db)

    # LLM returns non-JSON text
    from scripts import run_simulation
    monkeypatch.setattr(run_simulation, "_ask_humanizer", lambda prompt: "Sorry, I can't do that.")

    calls = run_simulation.humanize_comments(oasis_db)
    assert calls == 1  # LLM call succeeded, JSON parse failed

    # Verify DB is unchanged
    conn = sqlite3.connect(oasis_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT comment_id, content FROM comment ORDER BY comment_id").fetchall()
    conn.close()

    assert "pivotal testament" in rows[0]["content"]
