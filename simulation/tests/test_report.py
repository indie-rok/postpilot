"""Tests for generate_report.py — uses a mock SQLite DB."""

import os
import sys
import sqlite3
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from generate_report import (
    get_engagement_summary,
    get_comments,
    get_agent_actions,
    get_round_by_round,
    format_report,
)


@pytest.fixture
def mock_db():
    """Create a mock SQLite DB mimicking OASIS output schema."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE user (
            user_id INTEGER PRIMARY KEY, user_name TEXT, name TEXT,
            bio TEXT, num_followings INTEGER DEFAULT 0, num_followers INTEGER DEFAULT 0
        );
        CREATE TABLE post (
            post_id INTEGER PRIMARY KEY, user_id INTEGER, content TEXT,
            num_likes INTEGER DEFAULT 0, num_dislikes INTEGER DEFAULT 0,
            num_shares INTEGER DEFAULT 0, created_at TEXT
        );
        CREATE TABLE comment (
            comment_id INTEGER PRIMARY KEY, post_id INTEGER, user_id INTEGER,
            content TEXT, num_likes INTEGER DEFAULT 0, created_at TEXT
        );
        CREATE TABLE trace (
            trace_id INTEGER PRIMARY KEY, user_id INTEGER,
            action TEXT, info TEXT, created_at TEXT
        );
        CREATE TABLE "like" (user_id INTEGER, post_id INTEGER);
        CREATE TABLE dislike (user_id INTEGER, post_id INTEGER);
    """)

    cursor.execute("INSERT INTO user VALUES (1, 'op_user', 'OP', 'The poster', 0, 0)")
    cursor.execute(
        "INSERT INTO user VALUES (2, 'founder_early_01', 'Alex', 'SaaS founder', 0, 0)"
    )
    cursor.execute(
        "INSERT INTO user VALUES (3, 'skeptic_01', 'Jordan', 'Skeptical PM', 0, 0)"
    )
    cursor.execute("INSERT INTO user VALUES (4, 'lurker_01', 'Sam', 'Lurker', 0, 0)")
    cursor.execute("INSERT INTO user VALUES (5, 'hr_01', 'Priya', 'HR Lead', 0, 0)")

    cursor.execute(
        "INSERT INTO post VALUES (1, 1, 'Launch post content here', 3, 1, 0, '2026-03-22 10:00:00')"
    )

    cursor.execute(
        "INSERT INTO comment VALUES (1, 1, 2, 'Love this approach! 78%% completion is impressive.', 2, '2026-03-22 10:30:00')"
    )
    cursor.execute(
        "INSERT INTO comment VALUES (2, 1, 3, 'How is this different from Lattice? Pricing seems steep.', 0, '2026-03-22 11:00:00')"
    )
    cursor.execute(
        "INSERT INTO comment VALUES (3, 1, 5, 'Does it integrate with BambooHR?', 1, '2026-03-22 12:00:00')"
    )
    cursor.execute(
        "INSERT INTO comment VALUES (4, 1, 3, 'Show me real retention data, not just NPS.', 0, '2026-03-22 13:00:00')"
    )

    cursor.execute(
        "INSERT INTO trace VALUES (1, 2, 'like_post', '{\"post_id\": 1}', '2026-03-22 10:30:00')"
    )
    cursor.execute(
        "INSERT INTO trace VALUES (2, 3, 'create_comment', '{\"post_id\": 1}', '2026-03-22 11:00:00')"
    )
    cursor.execute(
        "INSERT INTO trace VALUES (3, 4, 'like_post', '{\"post_id\": 1}', '2026-03-22 14:00:00')"
    )
    cursor.execute(
        "INSERT INTO trace VALUES (4, 5, 'create_comment', '{\"post_id\": 1}', '2026-03-22 12:00:00')"
    )

    conn.commit()
    conn.close()
    yield db_path
    os.unlink(db_path)


def test_engagement_summary(mock_db):
    summary = get_engagement_summary(mock_db)
    assert summary["score"] == 2
    assert summary["num_likes"] == 3
    assert summary["num_dislikes"] == 1
    assert summary["comment_count"] == 4
    assert summary["total_agents"] == 5
    assert summary["engagement_rate"] > 0


def test_get_comments(mock_db):
    comments = get_comments(mock_db)
    assert len(comments) == 4
    assert any("Lattice" in c["content"] for c in comments)


def test_get_agent_actions(mock_db):
    actions = get_agent_actions(mock_db)
    assert len(actions) > 0
    for action in actions:
        assert "username" in action
        assert "action" in action


def test_format_report_contains_sections(mock_db):
    report = format_report(mock_db, skip_llm=True)
    assert "ENGAGEMENT SUMMARY" in report
    assert "AGENT-BY-AGENT REACTIONS" in report
    assert "ACTIONABLE INSIGHTS" in report
    assert "Score:" in report
