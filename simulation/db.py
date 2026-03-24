# pyright: reportAny=false, reportExplicitAny=false

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict, cast


def get_project_dir() -> Path:
    """Return the .post-pilot directory under cwd. Create if needed."""
    d = Path.cwd() / ".post-pilot"
    d.mkdir(exist_ok=True)
    return d


def get_default_db_path() -> str:
    return str(get_project_dir() / "post-pilot.db")


def get_env_path() -> Path:
    return get_project_dir() / ".env"


class CommunityProfileSeed(TypedDict):
    username: str
    realname: str
    bio: str
    persona: str
    age: int
    gender: str
    mbti: str
    country: str
    profession: str
    interested_topics: list[str]


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS community (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subreddit TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    scraped_at DATETIME,
    raw_data TEXT
);

CREATE TABLE IF NOT EXISTS community_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    community_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    realname TEXT NOT NULL,
    archetype TEXT NOT NULL,
    bio TEXT,
    persona TEXT NOT NULL,
    demographics TEXT,
    generated_at DATETIME NOT NULL,
    FOREIGN KEY (community_id) REFERENCES community(id)
);

CREATE TABLE IF NOT EXISTS run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag TEXT UNIQUE NOT NULL,
    community_id INTEGER,
    post_content TEXT NOT NULL,
    post_source TEXT NOT NULL DEFAULT 'manual',
    agent_count INTEGER NOT NULL,
    total_hours INTEGER NOT NULL,
    llm_model TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    post_likes INTEGER NOT NULL DEFAULT 0,
    post_dislikes INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    completed_at DATETIME,
    FOREIGN KEY (community_id) REFERENCES community(id)
);

CREATE TABLE IF NOT EXISTS run_agent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    profile_id INTEGER,
    username TEXT NOT NULL,
    realname TEXT NOT NULL,
    archetype TEXT NOT NULL,
    bio TEXT,
    persona TEXT NOT NULL,
    demographics TEXT,
    oasis_user_id INTEGER,
    engaged BOOLEAN NOT NULL DEFAULT 0,
    FOREIGN KEY (run_id) REFERENCES run(id)
);

CREATE TABLE IF NOT EXISTS run_comment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    agent_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    likes INTEGER NOT NULL DEFAULT 0,
    dislikes INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME,
    sentiment TEXT,
    FOREIGN KEY (run_id) REFERENCES run(id),
    FOREIGN KEY (agent_id) REFERENCES run_agent(id)
);

CREATE TABLE IF NOT EXISTS run_interview (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    agent_id INTEGER NOT NULL,
    response TEXT NOT NULL,
    clarity TEXT,
    would_click BOOLEAN,
    would_signup BOOLEAN,
    FOREIGN KEY (run_id) REFERENCES run(id),
    FOREIGN KEY (agent_id) REFERENCES run_agent(id)
);

CREATE TABLE IF NOT EXISTS run_scorecard (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER UNIQUE NOT NULL,
    score REAL,
    grade TEXT,
    summary TEXT,
    data TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (run_id) REFERENCES run(id)
);

CREATE TABLE IF NOT EXISTS product (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL,
    problem TEXT,
    features TEXT,
    audience TEXT,
    raw_context TEXT,
    onboarded INTEGER DEFAULT 0,
    batch_size INTEGER DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
"""


def init_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        _ = conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _ = conn.execute("PRAGMA foreign_keys = ON")
    return conn


def seed_default_community(db_path: str, profiles_path: str) -> None:
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        _ = cur.execute("SELECT id FROM community WHERE subreddit = ?", ("r/SaaS",))
        if cur.fetchone() is not None:
            return

        _ = cur.execute(
            """
            INSERT INTO community (subreddit, status, scraped_at, raw_data)
            VALUES (?, ?, ?, ?)
            """,
            ("r/SaaS", "active", None, None),
        )
        community_id = cur.lastrowid

        with open(profiles_path, "r", encoding="utf-8") as f:
            profiles = cast(list[CommunityProfileSeed], json.load(f))

        archetype_map = {
            "founder_early": "Early Founder",
            "founder_scaled": "Scaled Founder",
            "skeptic": "Skeptical PM",
            "indie": "Indie Hacker",
            "hr": "HR/People Ops",
            "lurker": "Lurker",
            "regular": "Community Regular",
            "vc": "VC/Growth",
        }
        generated_at = datetime.now(timezone.utc).isoformat()

        for profile in profiles:
            username = profile["username"]
            archetype = "Community Regular"
            for key, value in archetype_map.items():
                if username.startswith(key):
                    archetype = value
                    break

            demographics = {
                "age": profile.get("age"),
                "gender": profile.get("gender"),
                "mbti": profile.get("mbti"),
                "country": profile.get("country"),
                "profession": profile.get("profession"),
                "interested_topics": profile.get("interested_topics"),
            }

            _ = cur.execute(
                """
                INSERT INTO community_profile (
                    community_id, username, realname, archetype, bio, persona,
                    demographics, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    community_id,
                    username,
                    profile["realname"],
                    archetype,
                    profile.get("bio"),
                    profile["persona"],
                    json.dumps(demographics),
                    generated_at,
                ),
            )

        conn.commit()
    finally:
        conn.close()


def create_run(
    db_path: str,
    tag: str,
    community_id: int,
    post_content: str,
    agent_count: int,
    total_hours: int,
    llm_model: str | None = None,
) -> int:
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        _ = cur.execute(
            """
            INSERT INTO run (
                tag, community_id, post_content, agent_count, total_hours,
                llm_model, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tag,
                community_id,
                post_content,
                agent_count,
                total_hours,
                llm_model,
                "pending",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        if cur.lastrowid is None:
            raise RuntimeError("Failed to create run")
        return int(cur.lastrowid)
    finally:
        conn.close()


def create_run_agents(
    db_path: str, run_id: int, profiles: list[dict[str, Any]]
) -> list[tuple[int, str]]:
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        created: list[tuple[int, str]] = []
        for profile in profiles:
            _ = cur.execute(
                """
                INSERT INTO run_agent (
                    run_id, profile_id, username, realname, archetype, bio,
                    persona, demographics
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    profile["id"],
                    profile["username"],
                    profile["realname"],
                    profile["archetype"],
                    profile.get("bio"),
                    profile["persona"],
                    profile.get("demographics"),
                ),
            )
            if cur.lastrowid is None:
                raise RuntimeError("Failed to create run agent")
            created.append((int(cur.lastrowid), str(profile["username"])))

        conn.commit()
        return created
    finally:
        conn.close()


def update_run_status(
    db_path: str, run_id: int, status: str, completed_at: str | None = None
) -> None:
    conn = get_connection(db_path)
    try:
        if completed_at is None:
            _ = conn.execute(
                "UPDATE run SET status = ? WHERE id = ?",
                (status, run_id),
            )
        else:
            _ = conn.execute(
                "UPDATE run SET status = ?, completed_at = ? WHERE id = ?",
                (status, completed_at, run_id),
            )
        conn.commit()
    finally:
        conn.close()


def update_oasis_user_id(db_path: str, run_agent_id: int, oasis_user_id: int) -> None:
    conn = get_connection(db_path)
    try:
        _ = conn.execute(
            "UPDATE run_agent SET oasis_user_id = ? WHERE id = ?",
            (oasis_user_id, run_agent_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_agent_mapping(db_path: str, run_id: int) -> dict[str, int]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT username, id FROM run_agent WHERE run_id = ?",
            (run_id,),
        ).fetchall()
        return {str(row["username"]): int(row["id"]) for row in rows}
    finally:
        conn.close()


def extract_oasis_results(
    app_db_path: str,
    oasis_db_path: str,
    run_id: int,
    agent_mapping: dict[int, int],
) -> None:
    app_conn = get_connection(app_db_path)
    oasis_conn = sqlite3.connect(oasis_db_path)
    oasis_conn.row_factory = sqlite3.Row
    try:
        comments = oasis_conn.execute(
            "SELECT comment_id, user_id, content, created_at FROM comment"
        ).fetchall()

        inserted_comment_rows: list[tuple[int, int]] = []
        for comment in comments:
            oasis_user_id = int(comment["user_id"])
            agent_id = agent_mapping.get(oasis_user_id)
            if agent_id is None:
                continue

            cur = app_conn.execute(
                """
                INSERT INTO run_comment (run_id, agent_id, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, agent_id, str(comment["content"]), comment["created_at"]),
            )
            if cur.lastrowid is None:
                continue
            inserted_comment_rows.append(
                (int(cur.lastrowid), int(comment["comment_id"]))
            )

        for run_comment_id, oasis_comment_id in inserted_comment_rows:
            like_row = oasis_conn.execute(
                "SELECT COUNT(*) AS count FROM comment_like WHERE comment_id = ?",
                (oasis_comment_id,),
            ).fetchone()
            dislike_row = oasis_conn.execute(
                "SELECT COUNT(*) AS count FROM comment_dislike WHERE comment_id = ?",
                (oasis_comment_id,),
            ).fetchone()
            likes = int(like_row["count"]) if like_row is not None else 0
            dislikes = int(dislike_row["count"]) if dislike_row is not None else 0

            _ = app_conn.execute(
                "UPDATE run_comment SET likes = ?, dislikes = ? WHERE id = ?",
                (likes, dislikes, run_comment_id),
            )

        post_likes_row = oasis_conn.execute(
            'SELECT COUNT(*) AS count FROM "like"'
        ).fetchone()
        post_dislikes_row = oasis_conn.execute(
            "SELECT COUNT(*) AS count FROM dislike"
        ).fetchone()
        post_likes = int(post_likes_row["count"]) if post_likes_row is not None else 0
        post_dislikes = (
            int(post_dislikes_row["count"]) if post_dislikes_row is not None else 0
        )

        _ = app_conn.execute(
            "UPDATE run SET post_likes = ?, post_dislikes = ? WHERE id = ?",
            (post_likes, post_dislikes, run_id),
        )

        engaged_rows = oasis_conn.execute(
            """
            SELECT DISTINCT user_id
            FROM trace
            WHERE action NOT IN ('sign_up', 'refresh', 'do_nothing', 'interview')
            """
        ).fetchall()

        for row in engaged_rows:
            agent_id = agent_mapping.get(int(row["user_id"]))
            if agent_id is None:
                continue
            _ = app_conn.execute(
                "UPDATE run_agent SET engaged = 1 WHERE id = ? AND run_id = ?",
                (agent_id, run_id),
            )

        app_conn.commit()
    finally:
        oasis_conn.close()
        app_conn.close()


def insert_interview(
    db_path: str, run_id: int, agent_id: int | None, response: str
) -> None:
    if agent_id is None:
        return

    conn = get_connection(db_path)
    try:
        _ = conn.execute(
            "INSERT INTO run_interview (run_id, agent_id, response) VALUES (?, ?, ?)",
            (run_id, agent_id, response),
        )
        conn.commit()
    finally:
        conn.close()


def save_scorecard(
    db_path: str,
    run_id: int,
    score: float,
    grade: str,
    summary: str,
    data_json: str,
) -> None:
    conn = get_connection(db_path)
    try:
        _ = conn.execute(
            """
            INSERT OR REPLACE INTO run_scorecard (
                run_id, score, grade, summary, data, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                score,
                grade,
                summary,
                data_json,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def select_profiles_for_community(
    db_path: str, community_id: int, count: int
) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, username, realname, archetype, bio, persona, demographics
            FROM community_profile
            WHERE community_id = ?
            """,
            (community_id,),
        ).fetchall()
    finally:
        conn.close()

    by_archetype: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        profile = {
            "id": int(row["id"]),
            "username": str(row["username"]),
            "realname": str(row["realname"]),
            "archetype": str(row["archetype"]),
            "bio": row["bio"],
            "persona": str(row["persona"]),
            "demographics": row["demographics"],
        }
        by_archetype.setdefault(str(row["archetype"]), []).append(profile)

    if not by_archetype:
        raise RuntimeError(f"No profiles found for community {community_id}")

    archetype_names = sorted(by_archetype.keys())

    chosen: list[dict[str, Any]] = []
    chosen_ids: set[int] = set()

    idx = 0
    while len(chosen) < count:
        archetype = archetype_names[idx % len(archetype_names)]
        idx += 1
        pool = by_archetype.get(archetype, [])
        if not pool:
            if all(not by_archetype.get(name, []) for name in archetype_names):
                break
            continue
        picked = pool.pop(0)
        if picked["id"] not in chosen_ids:
            chosen.append(picked)
            chosen_ids.add(picked["id"])

    if len(chosen) < count:
        raise RuntimeError(f"Only {len(chosen)} profiles available, requested {count}")

    return chosen


def get_results_for_run(db_path: str, run_id: int) -> dict[str, Any]:
    conn = get_connection(db_path)
    try:
        run_row = conn.execute(
            """
            SELECT id, post_content, post_likes, post_dislikes, created_at
            FROM run
            WHERE id = ?
            """,
            (run_id,),
        ).fetchone()
        if run_row is None:
            raise RuntimeError(f"Run {run_id} not found")

        comment_rows = conn.execute(
            """
            SELECT c.id, c.content, c.likes, c.dislikes, c.created_at,
                   a.realname AS author, a.id AS user_id
            FROM run_comment c
            JOIN run_agent a ON c.agent_id = a.id
            WHERE c.run_id = ?
            ORDER BY c.created_at
            """,
            (run_id,),
        ).fetchall()

        agent_rows = conn.execute(
            """
            SELECT id, username, realname, archetype, bio
            FROM run_agent
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchall()

        total_agents_row = conn.execute(
            "SELECT COUNT(*) AS count FROM run_agent WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        commenting_agents_row = conn.execute(
            "SELECT COUNT(DISTINCT agent_id) AS count FROM run_comment WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        total_comments_row = conn.execute(
            "SELECT COUNT(*) AS count FROM run_comment WHERE run_id = ?",
            (run_id,),
        ).fetchone()

        likes = int(run_row["post_likes"])
        dislikes = int(run_row["post_dislikes"])

        post = {
            "id": int(run_row["id"]),
            "content": str(run_row["post_content"]),
            "likes": likes,
            "dislikes": dislikes,
            "created_at": run_row["created_at"],
        }

        comments = [
            {
                "id": int(row["id"]),
                "content": str(row["content"]),
                "likes": int(row["likes"]),
                "dislikes": int(row["dislikes"]),
                "created_at": row["created_at"],
                "author": str(row["author"]),
                "user_id": int(row["user_id"]),
            }
            for row in comment_rows
        ]

        profiles = {
            str(row["realname"]).lower(): {
                "username": str(row["username"]),
                "archetype": str(row["archetype"]),
                "bio": row["bio"],
            }
            for row in agent_rows
        }

        return {
            "post": post,
            "comments": comments,
            "profiles": profiles,
            "stats": {
                "score": likes - dislikes,
                "total_agents": int(total_agents_row["count"]),
                "commenting_agents": int(commenting_agents_row["count"]),
                "total_comments": int(total_comments_row["count"]),
            },
        }
    finally:
        conn.close()


def list_runs(db_path: str, community_id: int | None = None) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        query = """
            SELECT
                r.id,
                r.tag,
                r.status,
                r.community_id,
                r.agent_count,
                r.total_hours,
                r.llm_model,
                r.post_likes,
                r.post_dislikes,
                r.created_at,
                r.completed_at,
                (
                    SELECT COUNT(*)
                    FROM run_comment rc
                    WHERE rc.run_id = r.id
                ) AS comment_count,
                sc.grade,
                sc.score
            FROM run r
            LEFT JOIN run_scorecard sc ON sc.run_id = r.id
        """
        params: list[Any] = []
        if community_id is not None:
            query += " WHERE r.community_id = ?"
            params.append(community_id)
        query += " ORDER BY r.created_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def delete_run(db_path: str, run_id: int) -> None:
    conn = get_connection(db_path)
    try:
        _ = conn.execute("DELETE FROM run_scorecard WHERE run_id = ?", (run_id,))
        _ = conn.execute("DELETE FROM run_interview WHERE run_id = ?", (run_id,))
        _ = conn.execute("DELETE FROM run_comment WHERE run_id = ?", (run_id,))
        _ = conn.execute("DELETE FROM run_agent WHERE run_id = ?", (run_id,))
        _ = conn.execute("DELETE FROM run WHERE id = ?", (run_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Community CRUD
# ---------------------------------------------------------------------------


def get_community_by_subreddit(db_path: str, subreddit: str) -> dict[str, Any] | None:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id, subreddit, status, scraped_at, raw_data FROM community WHERE subreddit = ?",
            (subreddit,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


def create_community(
    db_path: str,
    subreddit: str,
    raw_data: str | None = None,
    status: str = "draft",
) -> int:
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        _ = cur.execute(
            """
            INSERT INTO community (subreddit, status, scraped_at, raw_data)
            VALUES (?, ?, ?, ?)
            """,
            (
                subreddit,
                status,
                datetime.now(timezone.utc).isoformat() if raw_data else None,
                raw_data,
            ),
        )
        conn.commit()
        if cur.lastrowid is None:
            raise RuntimeError("Failed to create community")
        return int(cur.lastrowid)
    finally:
        conn.close()


def save_community_profiles(
    db_path: str,
    community_id: int,
    profiles: list[dict[str, Any]],
    replace: bool = True,
) -> None:
    conn = get_connection(db_path)
    try:
        if replace:
            _ = conn.execute(
                "DELETE FROM community_profile WHERE community_id = ?",
                (community_id,),
            )

        generated_at = datetime.now(timezone.utc).isoformat()
        for profile in profiles:
            demographics = {}
            for key in [
                "age",
                "gender",
                "mbti",
                "country",
                "profession",
                "interested_topics",
            ]:
                if key in profile:
                    demographics[key] = profile[key]

            _ = conn.execute(
                """
                INSERT INTO community_profile (
                    community_id, username, realname, archetype, bio, persona,
                    demographics, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    community_id,
                    profile["username"],
                    profile["realname"],
                    profile["archetype"],
                    profile.get("bio"),
                    profile["persona"],
                    json.dumps(demographics),
                    generated_at,
                ),
            )

        _ = conn.execute(
            "UPDATE community SET status = 'active' WHERE id = ?",
            (community_id,),
        )
        conn.commit()
    finally:
        conn.close()


def get_all_profiles_for_community(
    db_path: str, community_id: int
) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, community_id, username, realname, archetype, bio, persona,
                   demographics, generated_at
            FROM community_profile
            WHERE community_id = ?
            ORDER BY archetype, username
            """,
            (community_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_profile(db_path: str, profile_id: int, fields: dict[str, Any]) -> None:
    allowed = {"username", "realname", "archetype", "bio", "persona"}
    updates: list[str] = []
    values: list[Any] = []

    for key, value in fields.items():
        if key in allowed:
            updates.append(f"{key} = ?")
            values.append(value)
        elif key == "demographics":
            updates.append("demographics = ?")
            values.append(json.dumps(value) if isinstance(value, dict) else value)

    if not updates:
        return

    values.append(profile_id)
    conn = get_connection(db_path)
    try:
        _ = conn.execute(
            f"UPDATE community_profile SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()


def delete_profile(db_path: str, profile_id: int) -> None:
    conn = get_connection(db_path)
    try:
        _ = conn.execute("DELETE FROM community_profile WHERE id = ?", (profile_id,))
        conn.commit()
    finally:
        conn.close()


def delete_community(db_path: str, community_id: int) -> None:
    conn = get_connection(db_path)
    try:
        _ = conn.execute(
            "DELETE FROM community_profile WHERE community_id = ?", (community_id,)
        )
        _ = conn.execute("DELETE FROM community WHERE id = ?", (community_id,))
        conn.commit()
    finally:
        conn.close()


def list_communities(db_path: str) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT c.id, c.subreddit, c.status, c.scraped_at,
                   (SELECT COUNT(*) FROM community_profile cp WHERE cp.community_id = c.id) AS profile_count
            FROM community c
            ORDER BY c.subreddit
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Product CRUD
# ---------------------------------------------------------------------------


def get_product(db_path: str) -> dict[str, Any] | None:
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM product WHERE id = 1").fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


def save_product(db_path: str, data: dict[str, Any]) -> None:
    conn = get_connection(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        _ = conn.execute(
            """
            INSERT INTO product (id, name, problem, features, audience,
                raw_context, onboarded, batch_size, created_at, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                problem = excluded.problem,
                features = excluded.features,
                audience = excluded.audience,
                raw_context = excluded.raw_context,
                onboarded = excluded.onboarded,
                batch_size = excluded.batch_size,
                updated_at = excluded.updated_at
            """,
            (
                data.get("name", ""),
                data.get("problem"),
                data.get("features"),
                data.get("audience"),
                data.get("raw_context"),
                data.get("onboarded", 0),
                data.get("batch_size", 0),
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
