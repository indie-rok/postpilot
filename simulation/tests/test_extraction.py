# pyright: reportMissingImports=false, reportImplicitRelativeImport=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportAny=false, reportUnusedCallResult=false, reportUnknownMemberType=false, reportUntypedFunctionDecorator=false

import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db import extract_oasis_results, get_connection, init_db, insert_interview


@pytest.fixture
def app_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def oasis_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


def _seed_app_db(db_path: str) -> None:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        _ = conn.execute(
            "INSERT INTO community (id, subreddit, status) VALUES (?, ?, ?)",
            (1, "r/SaaS", "active"),
        )
        _ = conn.execute(
            """
            INSERT INTO run (
                id, tag, community_id, post_content, post_source,
                agent_count, total_hours, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "extract-test",
                1,
                "Post body",
                "manual",
                2,
                24,
                "pending",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        _ = conn.execute(
            """
            INSERT INTO run_agent (
                id, run_id, username, realname, archetype, persona, engaged
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (100, 1, "agent_a", "Agent A", "Community Regular", "persona a", 0),
        )
        _ = conn.execute(
            """
            INSERT INTO run_agent (
                id, run_id, username, realname, archetype, persona, engaged
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (101, 1, "agent_b", "Agent B", "Community Regular", "persona b", 0),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_oasis_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        _ = conn.executescript(
            """
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
            CREATE TABLE comment_like (
                comment_like_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                comment_id INTEGER,
                created_at TEXT
            );
            CREATE TABLE comment_dislike (
                comment_dislike_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                comment_id INTEGER,
                created_at TEXT
            );
            CREATE TABLE like (
                like_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                post_id INTEGER,
                created_at TEXT
            );
            CREATE TABLE dislike (
                dislike_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                post_id INTEGER,
                created_at TEXT
            );
            CREATE TABLE trace (
                user_id INTEGER,
                created_at TEXT,
                action TEXT,
                info TEXT
            );
            """
        )

        _ = conn.execute(
            "INSERT INTO comment (comment_id, post_id, user_id, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (1, 1, 11, "mapped comment one", "2026-01-01T00:05:00+00:00"),
        )
        _ = conn.execute(
            "INSERT INTO comment (comment_id, post_id, user_id, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (2, 1, 22, "mapped comment two", "2026-01-01T00:10:00+00:00"),
        )
        _ = conn.execute(
            "INSERT INTO comment (comment_id, post_id, user_id, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (3, 1, 33, "unmapped comment", "2026-01-01T00:12:00+00:00"),
        )

        _ = conn.execute(
            "INSERT INTO comment_like (comment_like_id, user_id, comment_id, created_at) VALUES (?, ?, ?, ?)",
            (1, 90, 1, "2026-01-01T00:15:00+00:00"),
        )
        _ = conn.execute(
            "INSERT INTO comment_like (comment_like_id, user_id, comment_id, created_at) VALUES (?, ?, ?, ?)",
            (2, 91, 1, "2026-01-01T00:16:00+00:00"),
        )
        _ = conn.execute(
            "INSERT INTO comment_like (comment_like_id, user_id, comment_id, created_at) VALUES (?, ?, ?, ?)",
            (3, 92, 2, "2026-01-01T00:17:00+00:00"),
        )
        _ = conn.execute(
            "INSERT INTO comment_dislike (comment_dislike_id, user_id, comment_id, created_at) VALUES (?, ?, ?, ?)",
            (1, 95, 1, "2026-01-01T00:18:00+00:00"),
        )

        _ = conn.execute(
            "INSERT INTO like (like_id, user_id, post_id, created_at) VALUES (?, ?, ?, ?)",
            (1, 11, 1, "2026-01-01T00:20:00+00:00"),
        )
        _ = conn.execute(
            "INSERT INTO like (like_id, user_id, post_id, created_at) VALUES (?, ?, ?, ?)",
            (2, 22, 1, "2026-01-01T00:21:00+00:00"),
        )
        _ = conn.execute(
            "INSERT INTO like (like_id, user_id, post_id, created_at) VALUES (?, ?, ?, ?)",
            (3, 44, 1, "2026-01-01T00:22:00+00:00"),
        )
        _ = conn.execute(
            "INSERT INTO dislike (dislike_id, user_id, post_id, created_at) VALUES (?, ?, ?, ?)",
            (1, 50, 1, "2026-01-01T00:23:00+00:00"),
        )
        _ = conn.execute(
            "INSERT INTO dislike (dislike_id, user_id, post_id, created_at) VALUES (?, ?, ?, ?)",
            (2, 51, 1, "2026-01-01T00:24:00+00:00"),
        )

        _ = conn.execute(
            "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
            (11, "2026-01-01T00:30:00+00:00", "comment", "{}"),
        )
        _ = conn.execute(
            "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
            (22, "2026-01-01T00:31:00+00:00", "refresh", "{}"),
        )
        _ = conn.execute(
            "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
            (22, "2026-01-01T00:32:00+00:00", "like", "{}"),
        )
        _ = conn.execute(
            "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
            (33, "2026-01-01T00:33:00+00:00", "comment", "{}"),
        )
        _ = conn.execute(
            "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
            (11, "2026-01-01T00:34:00+00:00", "interview", "{}"),
        )
        conn.commit()
    finally:
        conn.close()


def test_extract_oasis_results_transfers_rows_and_updates_metrics(
    app_db_path, oasis_db_path
):
    _seed_app_db(app_db_path)
    _seed_oasis_db(oasis_db_path)

    extract_oasis_results(app_db_path, oasis_db_path, 1, {11: 100, 22: 101})

    conn = get_connection(app_db_path)
    try:
        comments = conn.execute(
            "SELECT agent_id, content, likes, dislikes FROM run_comment WHERE run_id = ? ORDER BY content",
            (1,),
        ).fetchall()
        assert len(comments) == 2
        assert comments[0]["agent_id"] == 100
        assert comments[0]["content"] == "mapped comment one"
        assert comments[0]["likes"] == 2
        assert comments[0]["dislikes"] == 1
        assert comments[1]["agent_id"] == 101
        assert comments[1]["content"] == "mapped comment two"
        assert comments[1]["likes"] == 1
        assert comments[1]["dislikes"] == 0

        run_row = conn.execute(
            "SELECT post_likes, post_dislikes FROM run WHERE id = ?",
            (1,),
        ).fetchone()
        assert run_row is not None
        assert run_row["post_likes"] == 3
        assert run_row["post_dislikes"] == 2

        agents = conn.execute(
            "SELECT id, engaged FROM run_agent WHERE run_id = ? ORDER BY id",
            (1,),
        ).fetchall()
        assert [row["id"] for row in agents] == [100, 101]
        assert [row["engaged"] for row in agents] == [1, 1]
    finally:
        conn.close()


def test_insert_interview_inserts_row_and_skips_none_agent(app_db_path):
    _seed_app_db(app_db_path)

    insert_interview(app_db_path, run_id=1, agent_id=None, response="ignored")
    insert_interview(
        app_db_path, run_id=1, agent_id=100, response="strong buying signal"
    )

    conn = get_connection(app_db_path)
    try:
        rows = conn.execute(
            "SELECT run_id, agent_id, response FROM run_interview ORDER BY id"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["run_id"] == 1
        assert rows[0]["agent_id"] == 100
        assert rows[0]["response"] == "strong buying signal"
    finally:
        conn.close()
