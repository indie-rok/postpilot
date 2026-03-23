# pyright: reportMissingImports=false, reportImplicitRelativeImport=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportAny=false, reportUnusedCallResult=false, reportUnknownMemberType=false, reportUntypedFunctionDecorator=false

import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db import (
    init_db,
    get_connection,
    seed_default_community,
    get_product,
    save_product,
)


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


def test_init_db_creates_tables(db_path):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {r[0] for r in cur.fetchall()}
    conn.close()
    expected = {
        "community",
        "community_profile",
        "run",
        "run_agent",
        "run_comment",
        "run_interview",
        "run_scorecard",
    }
    assert expected.issubset(tables)


def test_init_db_idempotent(db_path):
    init_db(db_path)
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM community")
    assert cur.fetchone()[0] == 0
    conn.close()


def test_get_connection(db_path):
    init_db(db_path)
    conn = get_connection(db_path)
    assert conn is not None
    conn.close()


def test_seed_default_community(db_path):
    init_db(db_path)
    profiles_path = os.path.join(
        os.path.dirname(__file__), "..", "profiles", "r_saas_community.json"
    )
    seed_default_community(db_path, profiles_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT subreddit, status FROM community WHERE id = 1")
    row = cur.fetchone()
    assert row[0] == "r/SaaS"
    assert row[1] == "active"

    cur.execute("SELECT COUNT(*) FROM community_profile WHERE community_id = 1")
    count = cur.fetchone()[0]
    assert count == 18

    cur.execute(
        "SELECT username, realname, archetype, bio, persona FROM community_profile LIMIT 1"
    )
    row = cur.fetchone()
    assert row[0] is not None
    assert row[1] is not None
    assert row[2] is not None
    assert row[3] is not None
    assert len(row[4]) > 100

    conn.close()


def test_seed_idempotent(db_path):
    init_db(db_path)
    profiles_path = os.path.join(
        os.path.dirname(__file__), "..", "profiles", "r_saas_community.json"
    )
    seed_default_community(db_path, profiles_path)
    seed_default_community(db_path, profiles_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM community")
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT COUNT(*) FROM community_profile")
    assert cur.fetchone()[0] == 18
    conn.close()


def test_get_product_returns_none_when_empty(db_path):
    init_db(db_path)
    assert get_product(db_path) is None


def test_save_and_get_product(db_path):
    init_db(db_path)
    save_product(
        db_path,
        {"name": "TestApp", "tagline": "A test app", "description": "Does testing"},
    )
    product = get_product(db_path)
    assert product is not None
    assert product["name"] == "TestApp"
    assert product["tagline"] == "A test app"


def test_save_product_upserts(db_path):
    init_db(db_path)
    save_product(db_path, {"name": "V1"})
    save_product(db_path, {"name": "V2", "tagline": "Updated"})
    product = get_product(db_path)
    assert product is not None
    assert product["name"] == "V2"
    assert product["tagline"] == "Updated"
