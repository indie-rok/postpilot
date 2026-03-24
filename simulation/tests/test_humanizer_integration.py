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
