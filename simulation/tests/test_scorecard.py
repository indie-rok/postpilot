import json
import os
import sqlite3
import tempfile

import pytest


@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE user (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER,
            user_name TEXT,
            name TEXT,
            bio TEXT,
            created_at DATETIME,
            num_followings INTEGER DEFAULT 0,
            num_followers INTEGER DEFAULT 0
        );
        CREATE TABLE post (
            post_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            content TEXT DEFAULT '',
            created_at DATETIME,
            num_likes INTEGER DEFAULT 0,
            num_dislikes INTEGER DEFAULT 0,
            num_shares INTEGER DEFAULT 0
        );
        CREATE TABLE comment (
            comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER,
            user_id INTEGER,
            content TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            num_likes INTEGER DEFAULT 0,
            num_dislikes INTEGER DEFAULT 0
        );
        CREATE TABLE trace (
            user_id INTEGER,
            created_at DATETIME,
            action TEXT,
            info TEXT
        );
        CREATE TABLE "like" (
            like_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            post_id INTEGER,
            created_at DATETIME
        );
        CREATE TABLE dislike (
            dislike_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            post_id INTEGER,
            created_at DATETIME
        );
    """
    )

    cur.execute(
        "INSERT INTO user VALUES (1, 1, 'skeptic_jordan', 'Jordan Lee', 'Sr PM', '2025-01-01', 0, 0)"
    )
    cur.execute(
        "INSERT INTO user VALUES (2, 2, 'founder_early_alex', 'Alex Chen', 'Founder', '2025-01-01', 0, 0)"
    )
    cur.execute(
        "INSERT INTO user VALUES (3, 3, 'indie_dev_mark', 'Mark Davis', 'Indie Dev', '2025-01-01', 0, 0)"
    )
    cur.execute(
        "INSERT INTO user VALUES (4, 4, 'lurker_sam', 'Sam Wilson', 'Lurker', '2025-01-01', 0, 0)"
    )
    cur.execute(
        "INSERT INTO user VALUES (5, 5, 'hr_sarah', 'Sarah Kim', 'HR Lead', '2025-01-01', 0, 0)"
    )

    cur.execute(
        "INSERT INTO post VALUES (1, 1, 'FlowPulse launch post', '2025-01-01 10:00:00', 3, 1, 0)"
    )

    cur.execute(
        "INSERT INTO comment VALUES (1, 1, 1, 'Pricing seems too high for early stage', '2025-01-01 10:05:00', 1, 0)"
    )
    cur.execute(
        "INSERT INTO comment VALUES (2, 1, 2, 'Love the privacy-first approach', '2025-01-01 10:10:00', 2, 0)"
    )
    cur.execute(
        "INSERT INTO comment VALUES (3, 1, 3, 'Would love a Slack integration', '2025-01-01 10:15:00', 0, 0)"
    )
    cur.execute(
        "INSERT INTO comment VALUES (4, 1, 5, 'The emoji check-ins are clever', '2025-01-01 10:20:00', 1, 0)"
    )

    cur.execute("INSERT INTO trace VALUES (1, '2025-01-01 10:00:00', 'sign_up', '{}')")
    cur.execute(
        "INSERT INTO trace VALUES (1, '2025-01-01 10:05:00', 'create_comment', '{}')"
    )
    cur.execute("INSERT INTO trace VALUES (2, '2025-01-01 10:00:00', 'sign_up', '{}')")
    cur.execute(
        "INSERT INTO trace VALUES (2, '2025-01-01 10:08:00', 'like_post', '{}')"
    )
    cur.execute(
        "INSERT INTO trace VALUES (2, '2025-01-01 10:10:00', 'create_comment', '{}')"
    )
    cur.execute("INSERT INTO trace VALUES (3, '2025-01-01 10:00:00', 'sign_up', '{}')")
    cur.execute(
        "INSERT INTO trace VALUES (3, '2025-01-01 10:15:00', 'create_comment', '{}')"
    )
    cur.execute("INSERT INTO trace VALUES (4, '2025-01-01 10:00:00', 'sign_up', '{}')")
    cur.execute("INSERT INTO trace VALUES (4, '2025-01-01 10:12:00', 'refresh', '{}')")
    cur.execute(
        "INSERT INTO trace VALUES (4, '2025-01-01 10:13:00', 'do_nothing', '{}')"
    )
    cur.execute("INSERT INTO trace VALUES (5, '2025-01-01 10:00:00', 'sign_up', '{}')")
    cur.execute(
        "INSERT INTO trace VALUES (5, '2025-01-01 10:20:00', 'create_comment', '{}')"
    )
    cur.execute(
        "INSERT INTO trace VALUES (5, '2025-01-01 10:21:00', 'like_post', '{}')"
    )

    cur.execute("INSERT INTO 'like' VALUES (1, 2, 1, '2025-01-01 10:08:00')")
    cur.execute("INSERT INTO 'like' VALUES (2, 5, 1, '2025-01-01 10:21:00')")
    cur.execute("INSERT INTO dislike VALUES (1, 1, 1, '2025-01-01 10:06:00')")

    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


@pytest.fixture
def profiles_path():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    profiles = [
        {"username": "skeptic_jordan", "realname": "Jordan Lee", "bio": "Sr PM"},
        {"username": "founder_early_alex", "realname": "Alex Chen", "bio": "Founder"},
        {"username": "indie_dev_mark", "realname": "Mark Davis", "bio": "Indie Dev"},
        {"username": "lurker_sam", "realname": "Sam Wilson", "bio": "Lurker"},
        {"username": "hr_sarah", "realname": "Sarah Kim", "bio": "HR Lead"},
    ]
    with open(path, "w") as f:
        json.dump(profiles, f)
    yield path
    os.unlink(path)


def test_query_engagement_metrics(test_db):
    from scripts.generate_scorecard import query_engagement_metrics

    m = query_engagement_metrics(test_db)
    assert m["post_score"] == 2
    assert m["num_likes"] == 3
    assert m["num_dislikes"] == 1
    assert m["comment_count"] == 4
    assert m["total_agents"] == 5
    assert m["engaged_agents"] == 4
    assert m["silent_agents"] == 1
    assert 75 <= m["engagement_rate"] <= 85


def test_query_archetype_participation(test_db, profiles_path):
    from scripts.generate_scorecard import query_archetype_participation

    p = query_archetype_participation(test_db, profiles_path)

    assert "Skeptical PM" in p
    assert p["Skeptical PM"]["commented"] == 1
    assert p["Skeptical PM"]["disliked"] >= 1

    assert "Early Founder" in p
    assert p["Early Founder"]["commented"] == 1
    assert p["Early Founder"]["liked"] >= 1

    assert "Lurker" in p
    assert p["Lurker"]["commented"] == 0
    assert p["Lurker"]["silent"] is True


def test_parse_llm_json_clean():
    from scripts.generate_scorecard import _parse_llm_json

    raw = '{"comments": [{"comment_id": 1, "sentiment": "positive"}]}'
    assert _parse_llm_json(raw) == {
        "comments": [{"comment_id": 1, "sentiment": "positive"}]
    }


def test_parse_llm_json_with_markdown_fences():
    from scripts.generate_scorecard import _parse_llm_json

    raw = '```json\n{"comments": [{"comment_id": 1, "sentiment": "negative"}]}\n```'
    assert _parse_llm_json(raw)["comments"][0]["sentiment"] == "negative"


def test_parse_llm_json_malformed_returns_empty():
    from scripts.generate_scorecard import _parse_llm_json

    result = _parse_llm_json("this is not json at all")
    assert result == {}


def test_classify_comments_returns_per_comment(monkeypatch):
    from scripts import generate_scorecard

    fake_response = json.dumps(
        {
            "comments": [
                {
                    "comment_id": 1,
                    "sentiment": "negative",
                    "topics": ["pricing"],
                    "is_objection": True,
                    "is_feature_request": False,
                    "feature_requested": None,
                },
                {
                    "comment_id": 2,
                    "sentiment": "positive",
                    "topics": ["privacy"],
                    "is_objection": False,
                    "is_feature_request": False,
                    "feature_requested": None,
                },
            ]
        }
    )
    monkeypatch.setattr(generate_scorecard, "_ask_llm", lambda prompt: fake_response)

    comments = [
        {
            "comment_id": 1,
            "content": "Too expensive",
            "author": "skeptic_jordan",
            "archetype": "Skeptical PM",
        },
        {
            "comment_id": 2,
            "content": "Great privacy focus",
            "author": "founder_early_alex",
            "archetype": "Early Founder",
        },
    ]
    result = generate_scorecard.classify_comments(comments)
    assert len(result) == 2
    assert result[0]["sentiment"] == "negative"
    assert result[1]["sentiment"] == "positive"
    assert result[0]["is_objection"] is True


def test_compute_grade_all_positive():
    from scripts.generate_scorecard import compute_grade

    grade, score = compute_grade(
        supportive_pct=100.0,
        engagement_rate=100.0,
        likes=10,
        dislikes=0,
        silent_agent_pct=0.0,
    )
    assert grade == "A+"
    assert score >= 90


def test_compute_grade_all_negative():
    from scripts.generate_scorecard import compute_grade

    grade, score = compute_grade(
        supportive_pct=0.0,
        engagement_rate=20.0,
        likes=0,
        dislikes=5,
        silent_agent_pct=80.0,
    )
    assert grade in ("D", "F")
    assert score < 30


def test_compute_grade_mixed():
    from scripts.generate_scorecard import compute_grade

    grade, score = compute_grade(
        supportive_pct=60.0,
        engagement_rate=80.0,
        likes=3,
        dislikes=1,
        silent_agent_pct=20.0,
    )
    assert grade in ("B+", "B", "A")


def test_build_scorecard_structure():
    from scripts.generate_scorecard import build_scorecard

    metrics = {
        "post_score": 2,
        "num_likes": 3,
        "num_dislikes": 1,
        "comment_count": 4,
        "total_agents": 5,
        "engaged_agents": 4,
        "silent_agents": 1,
        "engagement_rate": 80.0,
    }
    participation = {
        "Skeptical PM": {
            "total": 1,
            "commented": 1,
            "liked": 0,
            "disliked": 1,
            "silent_count": 0,
            "silent": False,
        },
        "Early Founder": {
            "total": 1,
            "commented": 1,
            "liked": 1,
            "disliked": 0,
            "silent_count": 0,
            "silent": False,
        },
        "Lurker": {
            "total": 1,
            "commented": 0,
            "liked": 0,
            "disliked": 0,
            "silent_count": 1,
            "silent": True,
        },
    }
    classifications = [
        {
            "comment_id": 1,
            "sentiment": "negative",
            "topics": ["pricing"],
            "is_objection": True,
            "is_feature_request": False,
            "feature_requested": None,
        },
        {
            "comment_id": 2,
            "sentiment": "positive",
            "topics": ["privacy"],
            "is_objection": False,
            "is_feature_request": False,
            "feature_requested": None,
        },
        {
            "comment_id": 3,
            "sentiment": "neutral",
            "topics": ["integration"],
            "is_objection": False,
            "is_feature_request": True,
            "feature_requested": "Slack integration",
        },
        {
            "comment_id": 4,
            "sentiment": "positive",
            "topics": ["ux", "check-ins"],
            "is_objection": False,
            "is_feature_request": False,
            "feature_requested": None,
        },
    ]
    comment_archetypes = {
        1: "Skeptical PM",
        2: "Early Founder",
        3: "Indie Hacker",
        4: "HR/People Ops",
    }

    sc = build_scorecard(metrics, participation, classifications, comment_archetypes)

    assert "grade" in sc
    assert "score" in sc
    assert "matrix" in sc
    assert "themes" in sc
    assert "strengths" in sc
    assert "problems" in sc
    assert "missing_features" in sc
    assert "metrics" in sc

    assert sc["matrix"]["Lurker"]["silent"] == 1
    assert len(sc["themes"]) > 0
    assert any(f["name"] == "Slack integration" for f in sc["missing_features"])


def test_build_scorecard_no_comments():
    from scripts.generate_scorecard import build_scorecard

    metrics = {
        "post_score": 0,
        "num_likes": 0,
        "num_dislikes": 0,
        "comment_count": 0,
        "total_agents": 3,
        "engaged_agents": 0,
        "silent_agents": 3,
        "engagement_rate": 0.0,
    }
    participation = {
        "Lurker": {
            "total": 3,
            "commented": 0,
            "liked": 0,
            "disliked": 0,
            "silent_count": 3,
            "silent": True,
        },
    }

    sc = build_scorecard(metrics, participation, [], {})
    assert sc["grade"] in ("D", "F")
    assert sc["themes"] == []
    assert sc["strengths"] == []
    assert sc["problems"] == []
    assert sc["missing_features"] == []


def test_generate_scorecard_full(test_db, profiles_path, monkeypatch):
    from scripts import generate_scorecard

    fake_response = json.dumps(
        {
            "comments": [
                {
                    "comment_id": 1,
                    "sentiment": "negative",
                    "topics": ["pricing"],
                    "is_objection": True,
                    "is_feature_request": False,
                    "feature_requested": None,
                },
                {
                    "comment_id": 2,
                    "sentiment": "positive",
                    "topics": ["privacy"],
                    "is_objection": False,
                    "is_feature_request": False,
                    "feature_requested": None,
                },
                {
                    "comment_id": 3,
                    "sentiment": "neutral",
                    "topics": ["integration"],
                    "is_objection": False,
                    "is_feature_request": True,
                    "feature_requested": "Slack integration",
                },
                {
                    "comment_id": 4,
                    "sentiment": "positive",
                    "topics": ["ux"],
                    "is_objection": False,
                    "is_feature_request": False,
                    "feature_requested": None,
                },
            ]
        }
    )
    monkeypatch.setattr(generate_scorecard, "_ask_llm", lambda prompt: fake_response)

    sc = generate_scorecard.generate_scorecard(test_db, profiles_path)

    assert sc["grade"] in ("A+", "A", "B+", "B", "C+", "C", "D", "F")
    assert isinstance(sc["score"], float)
    assert len(sc["matrix"]) > 0
    assert sc["metrics"]["comment_count"] == 4
