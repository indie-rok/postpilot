import json
import sqlite3
from datetime import datetime, timezone
from typing import TypedDict, cast


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
