# pyright: reportMissingImports=false, reportImplicitRelativeImport=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportAny=false, reportUnusedCallResult=false, reportUnknownMemberType=false, reportUntypedFunctionDecorator=false

import os
import sys
import tempfile
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db import (
    create_run,
    create_run_agents,
    delete_run,
    get_agent_mapping,
    get_connection,
    get_results_for_run,
    init_db,
    list_runs,
    seed_default_community,
    select_profiles_for_community,
    update_oasis_user_id,
    update_run_status,
)


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


def _seed(db_path: str) -> int:
    init_db(db_path)
    profiles_path = os.path.join(
        os.path.dirname(__file__), "..", "profiles", "r_saas_community.json"
    )
    seed_default_community(db_path, profiles_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM community WHERE subreddit = ?", ("r/SaaS",)
        ).fetchone()
        assert row is not None
        return int(row["id"])
    finally:
        conn.close()


def _sample_profiles(
    db_path: str, community_id: int, count: int = 3
) -> list[dict[str, object]]:
    return select_profiles_for_community(db_path, community_id, count)


def test_create_run_inserts_pending_row_and_returns_id(db_path):
    community_id = _seed(db_path)

    run_id = create_run(
        db_path,
        tag="run-create-1",
        community_id=community_id,
        post_content="hello world",
        agent_count=5,
        total_hours=24,
        llm_model="gpt-test",
    )

    assert run_id > 0

    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM run WHERE id = ?", (run_id,)).fetchone()
        assert row is not None
        assert row["status"] == "pending"
        assert row["created_at"] is not None
        assert row["llm_model"] == "gpt-test"
    finally:
        conn.close()


def test_create_run_agents_inserts_rows_with_profile_fields(db_path):
    community_id = _seed(db_path)
    run_id = create_run(db_path, "run-agents-1", community_id, "post", 3, 24)
    profiles = _sample_profiles(db_path, community_id, 3)

    inserted = create_run_agents(db_path, run_id, profiles)

    assert len(inserted) == 3
    usernames = {username for _, username in inserted}
    assert usernames == {p["username"] for p in profiles}

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM run_agent WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        assert len(rows) == 3
        for row in rows:
            source = next(p for p in profiles if p["username"] == row["username"])
            assert row["profile_id"] == source["id"]
            assert row["realname"] == source["realname"]
            assert row["archetype"] == source["archetype"]
            assert row["bio"] == source["bio"]
            assert row["persona"] == source["persona"]
            assert row["demographics"] == source["demographics"]
    finally:
        conn.close()


def test_update_run_status_updates_status_and_completed_at(db_path):
    community_id = _seed(db_path)
    run_id = create_run(db_path, "run-status-1", community_id, "post", 4, 12)

    update_run_status(db_path, run_id, "running")

    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT status, completed_at FROM run WHERE id = ?", (run_id,)
        ).fetchone()
        assert row is not None
        assert row["status"] == "running"
        assert row["completed_at"] is None
    finally:
        conn.close()

    completed = datetime.now(timezone.utc).isoformat()
    update_run_status(db_path, run_id, "completed", completed)

    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT status, completed_at FROM run WHERE id = ?", (run_id,)
        ).fetchone()
        assert row is not None
        assert row["status"] == "completed"
        assert row["completed_at"] == completed
    finally:
        conn.close()


def test_update_oasis_user_id_persists_value(db_path):
    community_id = _seed(db_path)
    run_id = create_run(db_path, "run-oasis-1", community_id, "post", 2, 6)
    profiles = _sample_profiles(db_path, community_id, 1)
    inserted = create_run_agents(db_path, run_id, profiles)
    run_agent_id = inserted[0][0]

    update_oasis_user_id(db_path, run_agent_id, 999)

    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT oasis_user_id FROM run_agent WHERE id = ?", (run_agent_id,)
        ).fetchone()
        assert row is not None
        assert row["oasis_user_id"] == 999
    finally:
        conn.close()


def test_get_agent_mapping_returns_username_to_run_agent_id(db_path):
    community_id = _seed(db_path)
    run_id = create_run(db_path, "run-map-1", community_id, "post", 3, 8)
    profiles = _sample_profiles(db_path, community_id, 3)
    inserted = create_run_agents(db_path, run_id, profiles)

    mapping = get_agent_mapping(db_path, run_id)

    expected = {username: run_agent_id for run_agent_id, username in inserted}
    assert mapping == expected


def test_select_profiles_for_community_returns_diverse_profiles(db_path):
    community_id = _seed(db_path)

    selected = select_profiles_for_community(db_path, community_id, 6)

    assert len(selected) == 6
    assert len({p["id"] for p in selected}) == 6
    archetypes = {p["archetype"] for p in selected}
    assert len(archetypes) >= 4


def test_get_results_for_run_returns_expected_shape_and_stats(db_path):
    community_id = _seed(db_path)
    run_id = create_run(
        db_path, "run-results-1", community_id, "A title\nBody text", 2, 24
    )
    profiles = _sample_profiles(db_path, community_id, 2)
    inserted = create_run_agents(db_path, run_id, profiles)

    conn = get_connection(db_path)
    try:
        _ = conn.execute(
            "UPDATE run SET post_likes = ?, post_dislikes = ? WHERE id = ?",
            (10, 3, run_id),
        )
        _ = conn.execute(
            "INSERT INTO run_comment (run_id, agent_id, content, likes, dislikes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_id,
                inserted[0][0],
                "first comment",
                5,
                1,
                "2026-01-01T00:00:00+00:00",
            ),
        )
        _ = conn.execute(
            "INSERT INTO run_comment (run_id, agent_id, content, likes, dislikes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_id,
                inserted[1][0],
                "second comment",
                2,
                0,
                "2026-01-01T01:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    result = get_results_for_run(db_path, run_id)

    assert set(result.keys()) == {"post", "comments", "profiles", "stats"}
    assert result["post"]["id"] == run_id
    assert result["post"]["likes"] == 10
    assert result["post"]["dislikes"] == 3
    assert len(result["comments"]) == 2
    assert result["comments"][0]["author"]
    assert result["stats"]["score"] == 7
    assert result["stats"]["total_agents"] == 2
    assert result["stats"]["commenting_agents"] == 2
    assert result["stats"]["total_comments"] == 2

    for profile in profiles:
        key = str(profile["realname"]).lower()
        assert key in result["profiles"]
        assert result["profiles"][key]["username"] == profile["username"]


def test_list_runs_returns_desc_order_with_comment_counts(db_path):
    community_id = _seed(db_path)
    first_id = create_run(db_path, "run-list-1", community_id, "post 1", 1, 6)
    second_id = create_run(db_path, "run-list-2", community_id, "post 2", 1, 6)
    profile = _sample_profiles(db_path, community_id, 1)
    first_agent_id = create_run_agents(db_path, first_id, profile)[0][0]
    second_agent_id = create_run_agents(db_path, second_id, profile)[0][0]

    conn = get_connection(db_path)
    try:
        _ = conn.execute(
            "UPDATE run SET created_at = ? WHERE id = ?",
            ("2026-01-01T00:00:00+00:00", first_id),
        )
        _ = conn.execute(
            "UPDATE run SET created_at = ? WHERE id = ?",
            ("2026-01-02T00:00:00+00:00", second_id),
        )
        _ = conn.execute(
            "INSERT INTO run_comment (run_id, agent_id, content) VALUES (?, ?, ?)",
            (first_id, first_agent_id, "c1"),
        )
        _ = conn.execute(
            "INSERT INTO run_comment (run_id, agent_id, content) VALUES (?, ?, ?)",
            (second_id, second_agent_id, "c2"),
        )
        _ = conn.execute(
            "INSERT INTO run_comment (run_id, agent_id, content) VALUES (?, ?, ?)",
            (second_id, second_agent_id, "c3"),
        )
        conn.commit()
    finally:
        conn.close()

    runs = list_runs(db_path)

    assert [runs[0]["id"], runs[1]["id"]] == [second_id, first_id]
    by_id = {row["id"]: row for row in runs}
    assert by_id[first_id]["comment_count"] == 1
    assert by_id[second_id]["comment_count"] == 2


def test_delete_run_removes_all_associated_data(db_path):
    community_id = _seed(db_path)
    run_id = create_run(db_path, "run-delete-1", community_id, "post", 1, 6)
    profile = _sample_profiles(db_path, community_id, 1)
    agent_id = create_run_agents(db_path, run_id, profile)[0][0]

    conn = get_connection(db_path)
    try:
        _ = conn.execute(
            "INSERT INTO run_comment (run_id, agent_id, content) VALUES (?, ?, ?)",
            (run_id, agent_id, "comment"),
        )
        _ = conn.execute(
            "INSERT INTO run_interview (run_id, agent_id, response) VALUES (?, ?, ?)",
            (run_id, agent_id, "response"),
        )
        _ = conn.execute(
            "INSERT INTO run_scorecard (run_id, score, grade, summary, data, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, 0.0, "F", "summary", "{}", "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    delete_run(db_path, run_id)

    conn = get_connection(db_path)
    try:
        for table in [
            "run_scorecard",
            "run_interview",
            "run_comment",
            "run_agent",
            "run",
        ]:
            row = conn.execute(
                f"SELECT COUNT(*) AS count FROM {table} WHERE run_id = ?"
                if table != "run"
                else "SELECT COUNT(*) AS count FROM run WHERE id = ?",
                (run_id,),
            ).fetchone()
            assert row is not None
            assert row["count"] == 0
    finally:
        conn.close()
