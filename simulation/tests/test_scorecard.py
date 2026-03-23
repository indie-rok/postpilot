# pyright: reportMissingImports=false, reportImplicitRelativeImport=false

import json
import os
import sqlite3
import tempfile

import pytest

from db import get_connection, init_db


@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    conn = get_connection(path)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO run (
            id, tag, community_id, post_content, post_source, agent_count,
            total_hours, status, post_likes, post_dislikes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            "test-run",
            None,
            "FlowPulse launch post",
            "manual",
            5,
            24,
            "completed",
            3,
            1,
            "2025-01-01 10:00:00",
        ),
    )

    agent_rows = [
        (1, 1, "skeptic_jordan", "Jordan Lee", "Skeptical PM", "Sr PM", "persona", 1),
        (
            2,
            1,
            "founder_early_alex",
            "Alex Chen",
            "Early Founder",
            "Founder",
            "persona",
            1,
        ),
        (
            3,
            1,
            "indie_dev_mark",
            "Mark Davis",
            "Indie Hacker",
            "Indie Dev",
            "persona",
            1,
        ),
        (4, 1, "lurker_sam", "Sam Wilson", "Lurker", "Lurker", "persona", 0),
        (5, 1, "hr_sarah", "Sarah Kim", "HR/People Ops", "HR Lead", "persona", 1),
    ]
    for row in agent_rows:
        cur.execute(
            """
            INSERT INTO run_agent (
                id, run_id, username, realname, archetype, bio, persona, engaged
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )

    comment_rows = [
        (1, 1, 1, "Pricing seems too high for early stage", "2025-01-01 10:05:00"),
        (2, 1, 2, "Love the privacy-first approach", "2025-01-01 10:10:00"),
        (3, 1, 3, "Would love a Slack integration", "2025-01-01 10:15:00"),
        (4, 1, 5, "The emoji check-ins are clever", "2025-01-01 10:20:00"),
    ]
    for cid, run_id, agent_id, content, created_at in comment_rows:
        cur.execute(
            """
            INSERT INTO run_comment (
                id, run_id, agent_id, content, likes, dislikes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cid, run_id, agent_id, content, 0, 0, created_at),
        )

    cur.execute(
        """
        INSERT INTO run_interview (
            run_id, agent_id, response, clarity, would_click, would_signup
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (1, 1, "Seems like a burnout dashboard for startup teams.", "partial", 1, 0),
    )

    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


def test_query_engagement_metrics(test_db):
    from scripts.generate_scorecard import query_engagement_metrics

    m = query_engagement_metrics(test_db, 1)
    assert m["post_score"] == 2
    assert m["num_likes"] == 3
    assert m["num_dislikes"] == 1
    assert m["comment_count"] == 4
    assert m["total_agents"] == 5
    assert m["engaged_agents"] == 4
    assert m["silent_agents"] == 1
    assert 75 <= m["engagement_rate"] <= 85


def test_query_archetype_participation(test_db):
    from scripts.generate_scorecard import query_archetype_participation

    p = query_archetype_participation(test_db, 1)

    assert "Skeptical PM" in p
    assert p["Skeptical PM"]["commented"] == 1

    assert "Early Founder" in p
    assert p["Early Founder"]["commented"] == 1

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
                    "topics": ["pricing too high for startups"],
                    "is_objection": True,
                    "is_feature_request": False,
                    "feature_requested": None,
                    "objection_type": "pricing",
                    "would_click_link": "unlikely",
                    "would_signup": "no",
                    "understands_product": "yes",
                    "would_recommend": "no",
                    "is_question": False,
                    "mentions_competitor": False,
                    "competitor_name": None,
                    "mentions_pricing": True,
                },
                {
                    "comment_id": 2,
                    "sentiment": "positive",
                    "topics": ["privacy-first approach praised"],
                    "is_objection": False,
                    "is_feature_request": False,
                    "feature_requested": None,
                    "objection_type": None,
                    "would_click_link": "yes",
                    "would_signup": "likely",
                    "understands_product": "yes",
                    "would_recommend": "yes",
                    "is_question": False,
                    "mentions_competitor": False,
                    "competitor_name": None,
                    "mentions_pricing": False,
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
    assert result[0]["objection_type"] == "pricing"
    assert result[1]["would_click_link"] == "yes"
    assert result[0]["mentions_pricing"] is True


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
            "topics": ["pricing too high"],
            "is_objection": True,
            "is_feature_request": False,
            "feature_requested": None,
            "objection_type": "pricing",
            "would_click_link": "unlikely",
            "would_signup": "no",
            "understands_product": "yes",
            "would_recommend": "no",
            "is_question": False,
            "mentions_competitor": True,
            "competitor_name": "OfficeVibe",
            "mentions_pricing": True,
        },
        {
            "comment_id": 2,
            "sentiment": "positive",
            "topics": ["privacy praised"],
            "is_objection": False,
            "is_feature_request": False,
            "feature_requested": None,
            "objection_type": None,
            "would_click_link": "yes",
            "would_signup": "likely",
            "understands_product": "yes",
            "would_recommend": "yes",
            "is_question": False,
            "mentions_competitor": False,
            "competitor_name": None,
            "mentions_pricing": False,
        },
        {
            "comment_id": 3,
            "sentiment": "neutral",
            "topics": ["integration needs"],
            "is_objection": False,
            "is_feature_request": True,
            "feature_requested": "Slack integration",
            "objection_type": None,
            "would_click_link": "likely",
            "would_signup": "unlikely",
            "understands_product": "partially",
            "would_recommend": "maybe",
            "is_question": True,
            "mentions_competitor": False,
            "competitor_name": None,
            "mentions_pricing": False,
        },
        {
            "comment_id": 4,
            "sentiment": "positive",
            "topics": ["ux praised", "check-ins clever"],
            "is_objection": False,
            "is_feature_request": False,
            "feature_requested": None,
            "objection_type": None,
            "would_click_link": "yes",
            "would_signup": "yes",
            "understands_product": "yes",
            "would_recommend": "yes",
            "is_question": False,
            "mentions_competitor": False,
            "competitor_name": None,
            "mentions_pricing": False,
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

    assert "click_through" in sc
    assert sc["click_through"]["count"] == 3
    assert sc["click_through"]["total"] == 5
    assert sc["click_through"]["rate"] == 60.0
    assert "signup_funnel" in sc
    assert "message_clarity" in sc
    assert sc["message_clarity"]["clear"] == 3
    assert sc["message_clarity"]["partial"] == 1
    assert sc["message_clarity"]["confused"] == 0
    assert "objection_map" in sc
    assert len(sc["objection_map"]) == 1
    assert sc["objection_map"][0]["type"] == "pricing"
    assert "competitive_mentions" in sc
    assert sc["competitive_mentions"][0]["name"] == "OfficeVibe"
    assert "question_density" in sc
    assert sc["question_density"]["count"] == 1
    assert "pricing_sensitivity" in sc
    assert sc["pricing_sensitivity"]["mentioned"] == 1
    assert "word_of_mouth" in sc
    assert "hook_effectiveness" in sc
    assert "audience_fit" in sc
    assert "sentiment_drift" in sc
    assert "engagement_decay" in sc
    assert "engagement_depth" in sc


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


def test_generate_scorecard_full(test_db, monkeypatch):
    from scripts import generate_scorecard

    fake_comment_response = json.dumps(
        {
            "comments": [
                {
                    "comment_id": 1,
                    "sentiment": "negative",
                    "topics": ["pricing too steep"],
                    "is_objection": True,
                    "is_feature_request": False,
                    "feature_requested": None,
                    "objection_type": "pricing",
                    "would_click_link": "unlikely",
                    "would_signup": "no",
                    "understands_product": "yes",
                    "would_recommend": "no",
                    "is_question": False,
                    "mentions_competitor": False,
                    "competitor_name": None,
                    "mentions_pricing": True,
                },
                {
                    "comment_id": 2,
                    "sentiment": "positive",
                    "topics": ["privacy approach"],
                    "is_objection": False,
                    "is_feature_request": False,
                    "feature_requested": None,
                    "objection_type": None,
                    "would_click_link": "yes",
                    "would_signup": "likely",
                    "understands_product": "yes",
                    "would_recommend": "yes",
                    "is_question": False,
                    "mentions_competitor": False,
                    "competitor_name": None,
                    "mentions_pricing": False,
                },
                {
                    "comment_id": 3,
                    "sentiment": "neutral",
                    "topics": ["integration question"],
                    "is_objection": False,
                    "is_feature_request": True,
                    "feature_requested": "Slack integration",
                    "objection_type": None,
                    "would_click_link": "likely",
                    "would_signup": "unlikely",
                    "understands_product": "partially",
                    "would_recommend": "maybe",
                    "is_question": True,
                    "mentions_competitor": False,
                    "competitor_name": None,
                    "mentions_pricing": False,
                },
                {
                    "comment_id": 4,
                    "sentiment": "positive",
                    "topics": ["ux praised"],
                    "is_objection": False,
                    "is_feature_request": False,
                    "feature_requested": None,
                    "objection_type": None,
                    "would_click_link": "yes",
                    "would_signup": "yes",
                    "understands_product": "yes",
                    "would_recommend": "yes",
                    "is_question": False,
                    "mentions_competitor": False,
                    "competitor_name": None,
                    "mentions_pricing": False,
                },
            ]
        }
    )
    fake_interview_response = json.dumps(
        {
            "ratings": [
                {
                    "index": 1,
                    "clarity": "accurate",
                    "would_click": "yes",
                    "would_signup": "likely",
                }
            ]
        }
    )

    def _fake_ask_llm(prompt: str) -> str:
        if "Rate each person's understanding" in prompt:
            return fake_interview_response
        return fake_comment_response

    monkeypatch.setattr(generate_scorecard, "_ask_llm", _fake_ask_llm)

    sc = generate_scorecard.generate_scorecard(test_db, 1)

    assert sc["grade"] in ("A+", "A", "B+", "B", "C+", "C", "D", "F")
    assert isinstance(sc["score"], float)
    assert len(sc["matrix"]) > 0
    assert sc["metrics"]["comment_count"] == 4
    assert "click_through" in sc
    assert "signup_funnel" in sc
    assert "message_clarity" in sc
    assert "objection_map" in sc
    assert "engagement_decay" in sc
    assert "engagement_depth" in sc
    assert "audience_fit" in sc

    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute(
        "SELECT score, grade, summary, data FROM run_scorecard WHERE run_id = ?", (1,)
    )
    row = cur.fetchone()
    conn.close()
    assert row is not None
    assert row[1] == sc["grade"]
    assert json.loads(row[3])["metrics"]["comment_count"] == 4
