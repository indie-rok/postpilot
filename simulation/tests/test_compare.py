"""Tests for compare_runs.py — uses mock SQLite DBs."""

import os
import sys
import sqlite3
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from compare_runs import load_run_metrics, determine_winner, format_comparison


def _create_mock_db(num_likes, num_dislikes, num_comments):
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.executescript("""
        CREATE TABLE user (user_id INTEGER PRIMARY KEY, user_name TEXT, name TEXT, bio TEXT, num_followings INTEGER DEFAULT 0, num_followers INTEGER DEFAULT 0);
        CREATE TABLE post (post_id INTEGER PRIMARY KEY, user_id INTEGER, content TEXT, num_likes INTEGER DEFAULT 0, num_dislikes INTEGER DEFAULT 0, num_shares INTEGER DEFAULT 0, created_at TEXT);
        CREATE TABLE comment (comment_id INTEGER PRIMARY KEY, post_id INTEGER, user_id INTEGER, content TEXT, num_likes INTEGER DEFAULT 0, created_at TEXT);
        CREATE TABLE trace (trace_id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT, info TEXT, created_at TEXT);
    """)
    cursor.execute("INSERT INTO user VALUES (1, 'op', 'OP', 'bio', 0, 0)")
    cursor.execute(
        f"INSERT INTO post VALUES (1, 1, 'content', {num_likes}, {num_dislikes}, 0, '2026-01-01')"
    )
    for i in range(num_comments):
        cursor.execute(
            f"INSERT INTO comment VALUES ({i + 1}, 1, 1, 'comment {i}', 0, '2026-01-01')"
        )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def mock_dbs():
    paths = [
        _create_mock_db(num_likes=10, num_dislikes=2, num_comments=8),  # score 8
        _create_mock_db(
            num_likes=15, num_dislikes=3, num_comments=5
        ),  # score 12 (winner)
        _create_mock_db(num_likes=7, num_dislikes=1, num_comments=12),  # score 6
    ]
    yield paths
    for p in paths:
        os.unlink(p)


def test_load_run_metrics(mock_dbs):
    metrics = load_run_metrics(mock_dbs[0])
    assert metrics["score"] == 8
    assert metrics["num_likes"] == 10
    assert metrics["comment_count"] == 8


def test_determine_winner(mock_dbs):
    all_metrics = [
        {"tag": "v1", **load_run_metrics(mock_dbs[0])},
        {"tag": "v2", **load_run_metrics(mock_dbs[1])},
        {"tag": "v3", **load_run_metrics(mock_dbs[2])},
    ]
    winner = determine_winner(all_metrics)
    assert winner["tag"] == "v2"


def test_format_comparison(mock_dbs):
    all_metrics = [
        {"tag": "v1", **load_run_metrics(mock_dbs[0])},
        {"tag": "v2", **load_run_metrics(mock_dbs[1])},
        {"tag": "v3", **load_run_metrics(mock_dbs[2])},
    ]
    output = format_comparison(all_metrics)
    assert "v1" in output
    assert "v2" in output
    assert "v3" in output
    assert "WINNER" in output or "winner" in output.lower()
