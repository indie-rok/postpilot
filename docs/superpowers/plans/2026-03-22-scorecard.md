# Scorecard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Analysis tab's free-form LLM prose with a structured, frequency-based scorecard showing reception grade, archetype×sentiment matrix, top themes, strengths/problems, and missing features.

**Architecture:** SQL queries extract hard numbers from the OASIS SQLite DB (engagement, archetype participation, silent agents). A single LLM call classifies each comment (sentiment, topics, objections, feature requests). Python merges both into a `ScorecardData` dict. The UI renders structured cards from JSON.

**Tech Stack:** Python 3.11, SQLite, CAMEL (OpenAI-compatible LLM), FastAPI, vanilla JS/HTML/CSS

**Spec:** `docs/superpowers/specs/2026-03-22-scorecard-design.md`

---

## File Structure

| File | Role |
|---|---|
| `scripts/generate_scorecard.py` | NEW — SQL queries, LLM classification, merge logic, grade computation |
| `tests/test_scorecard.py` | NEW — Unit tests for all scorecard functions |
| `server.py` | MODIFY — Add `/api/scorecard/{tag}`, add `/api/rewrite/{tag}`, deprecate `/api/analyze/{tag}` |
| `static/index.html` | MODIFY — Replace Analysis tab content with scorecard card layout |

---

### Task 1: Scorecard SQL Queries + Tests

**Files:**
- Create: `scripts/generate_scorecard.py`
- Create: `tests/test_scorecard.py`

- [ ] **Step 1: Create test DB fixture and test for `query_engagement_metrics`**

Create `tests/test_scorecard.py`:

```python
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

    cur.executescript("""
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
    """)

    cur.execute("INSERT INTO user VALUES (1, 1, 'skeptic_jordan', 'Jordan Lee', 'Sr PM', '2025-01-01', 0, 0)")
    cur.execute("INSERT INTO user VALUES (2, 2, 'founder_early_alex', 'Alex Chen', 'Founder', '2025-01-01', 0, 0)")
    cur.execute("INSERT INTO user VALUES (3, 3, 'indie_dev_mark', 'Mark Davis', 'Indie Dev', '2025-01-01', 0, 0)")
    cur.execute("INSERT INTO user VALUES (4, 4, 'lurker_sam', 'Sam Wilson', 'Lurker', '2025-01-01', 0, 0)")
    cur.execute("INSERT INTO user VALUES (5, 5, 'hr_sarah', 'Sarah Kim', 'HR Lead', '2025-01-01', 0, 0)")

    cur.execute("INSERT INTO post VALUES (1, 1, 'FlowPulse launch post', '2025-01-01 10:00:00', 3, 1, 0)")

    cur.execute("INSERT INTO comment VALUES (1, 1, 1, 'Pricing seems too high for early stage', '2025-01-01 10:05:00', 1, 0)")
    cur.execute("INSERT INTO comment VALUES (2, 1, 2, 'Love the privacy-first approach', '2025-01-01 10:10:00', 2, 0)")
    cur.execute("INSERT INTO comment VALUES (3, 1, 3, 'Would love a Slack integration', '2025-01-01 10:15:00', 0, 0)")
    cur.execute("INSERT INTO comment VALUES (4, 1, 5, 'The emoji check-ins are clever', '2025-01-01 10:20:00', 1, 0)")

    cur.execute("INSERT INTO trace VALUES (1, '2025-01-01 10:00:00', 'sign_up', '{}')")
    cur.execute("INSERT INTO trace VALUES (1, '2025-01-01 10:05:00', 'create_comment', '{}')")
    cur.execute("INSERT INTO trace VALUES (2, '2025-01-01 10:00:00', 'sign_up', '{}')")
    cur.execute("INSERT INTO trace VALUES (2, '2025-01-01 10:08:00', 'like_post', '{}')")
    cur.execute("INSERT INTO trace VALUES (2, '2025-01-01 10:10:00', 'create_comment', '{}')")
    cur.execute("INSERT INTO trace VALUES (3, '2025-01-01 10:00:00', 'sign_up', '{}')")
    cur.execute("INSERT INTO trace VALUES (3, '2025-01-01 10:15:00', 'create_comment', '{}')")
    cur.execute("INSERT INTO trace VALUES (4, '2025-01-01 10:00:00', 'sign_up', '{}')")
    cur.execute("INSERT INTO trace VALUES (4, '2025-01-01 10:12:00', 'refresh', '{}')")
    cur.execute("INSERT INTO trace VALUES (4, '2025-01-01 10:13:00', 'do_nothing', '{}')")
    cur.execute("INSERT INTO trace VALUES (5, '2025-01-01 10:00:00', 'sign_up', '{}')")
    cur.execute("INSERT INTO trace VALUES (5, '2025-01-01 10:20:00', 'create_comment', '{}')")
    cur.execute("INSERT INTO trace VALUES (5, '2025-01-01 10:21:00', 'like_post', '{}')")

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
    assert m["post_score"] == 2  # 3 likes - 1 dislike
    assert m["num_likes"] == 3
    assert m["num_dislikes"] == 1
    assert m["comment_count"] == 4
    assert m["total_agents"] == 5
    assert m["engaged_agents"] == 4  # jordan, alex, mark, sarah (not lurker_sam)
    assert m["silent_agents"] == 1   # lurker_sam
    assert 75 <= m["engagement_rate"] <= 85  # 4/5 = 80%


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
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd simulation && python -m pytest tests/test_scorecard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.generate_scorecard'`

- [ ] **Step 3: Implement SQL query functions**

Create `scripts/generate_scorecard.py`:

```python
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

ARCHETYPE_PREFIXES = {
    "founder_early": "Early Founder",
    "founder_scaled": "Scaled Founder",
    "skeptic": "Skeptical PM",
    "indie": "Indie Hacker",
    "hr": "HR/People Ops",
    "lurker": "Lurker",
    "regular": "Community Regular",
    "vc": "VC/Growth",
}

SILENT_ACTIONS = {"sign_up", "refresh", "do_nothing"}


def _archetype_for(username: str) -> str:
    for prefix, label in ARCHETYPE_PREFIXES.items():
        if prefix in username:
            return label
    return "Other"


def query_engagement_metrics(db_path: str) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "SELECT COALESCE(SUM(num_likes), 0), COALESCE(SUM(num_dislikes), 0) FROM post"
    )
    num_likes, num_dislikes = cur.fetchone()

    cur.execute("SELECT COUNT(*) FROM comment")
    comment_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM user")
    total_agents = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(DISTINCT user_id) FROM trace "
        "WHERE action NOT IN ('sign_up', 'refresh', 'do_nothing')"
    )
    engaged_agents = cur.fetchone()[0]

    conn.close()

    silent_agents = total_agents - engaged_agents
    engagement_rate = (engaged_agents / total_agents * 100) if total_agents else 0.0

    return {
        "post_score": num_likes - num_dislikes,
        "num_likes": num_likes,
        "num_dislikes": num_dislikes,
        "comment_count": comment_count,
        "total_agents": total_agents,
        "engaged_agents": engaged_agents,
        "silent_agents": silent_agents,
        "engagement_rate": round(engagement_rate, 1),
    }


def query_archetype_participation(
    db_path: str, profiles_path: str
) -> dict[str, dict[str, Any]]:
    with open(profiles_path) as f:
        profiles = json.load(f)

    user_archetype: dict[str, str] = {}
    for p in profiles:
        user_archetype[p["username"]] = _archetype_for(p["username"])

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT user_id, COALESCE(user_name, name) FROM user")
    id_to_name: dict[int, str] = {}
    for uid, uname in cur.fetchall():
        id_to_name[uid] = uname or ""

    cur.execute("SELECT user_id, action FROM trace")
    user_actions: dict[int, set[str]] = {}
    for uid, action in cur.fetchall():
        user_actions.setdefault(uid, set()).add(action)

    cur.execute("SELECT DISTINCT user_id FROM comment WHERE post_id = 1")
    commenters = {r[0] for r in cur.fetchall()}

    cur.execute("SELECT DISTINCT user_id FROM 'like'")
    likers = {r[0] for r in cur.fetchall()}

    cur.execute("SELECT DISTINCT user_id FROM dislike")
    dislikers = {r[0] for r in cur.fetchall()}

    conn.close()

    result: dict[str, dict[str, Any]] = {}

    for uid, uname in id_to_name.items():
        archetype = user_archetype.get(uname, _archetype_for(uname))
        if archetype not in result:
            result[archetype] = {
                "total": 0,
                "commented": 0,
                "liked": 0,
                "disliked": 0,
                "silent_count": 0,
                "silent": False,
            }
        entry = result[archetype]
        entry["total"] += 1

        actions = user_actions.get(uid, set())
        meaningful = actions - SILENT_ACTIONS
        is_engaged = bool(meaningful) or uid in commenters or uid in likers or uid in dislikers

        if uid in commenters:
            entry["commented"] += 1
        if uid in likers:
            entry["liked"] += 1
        if uid in dislikers:
            entry["disliked"] += 1
        if not is_engaged:
            entry["silent_count"] += 1

    for entry in result.values():
        entry["silent"] = entry["silent_count"] == entry["total"]

    return result
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd simulation && python -m pytest tests/test_scorecard.py::test_query_engagement_metrics tests/test_scorecard.py::test_query_archetype_participation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_scorecard.py tests/test_scorecard.py
git commit -m "feat(scorecard): add SQL query functions for engagement metrics and archetype participation"
```

---

### Task 2: LLM Classification + JSON Parsing

**Files:**
- Modify: `scripts/generate_scorecard.py`
- Modify: `tests/test_scorecard.py`

- [ ] **Step 1: Add tests for `_parse_llm_json` and `classify_comments`**

Append to `tests/test_scorecard.py`:

```python
def test_parse_llm_json_clean():
    from scripts.generate_scorecard import _parse_llm_json

    raw = '{"comments": [{"comment_id": 1, "sentiment": "positive"}]}'
    assert _parse_llm_json(raw) == {"comments": [{"comment_id": 1, "sentiment": "positive"}]}


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

    fake_response = json.dumps({
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
    })
    monkeypatch.setattr(generate_scorecard, "_ask_llm", lambda prompt: fake_response)

    comments = [
        {"comment_id": 1, "content": "Too expensive", "author": "skeptic_jordan", "archetype": "Skeptical PM"},
        {"comment_id": 2, "content": "Great privacy focus", "author": "founder_early_alex", "archetype": "Early Founder"},
    ]
    result = generate_scorecard.classify_comments(comments)
    assert len(result) == 2
    assert result[0]["sentiment"] == "negative"
    assert result[1]["sentiment"] == "positive"
    assert result[0]["is_objection"] is True
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd simulation && python -m pytest tests/test_scorecard.py::test_parse_llm_json_clean tests/test_scorecard.py::test_classify_comments_returns_per_comment -v`
Expected: FAIL

- [ ] **Step 3: Implement LLM classification functions**

Append to `scripts/generate_scorecard.py`:

```python
def _create_model():
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType

    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=os.getenv("LLM_MODEL", "arcee-ai/trinity-mini:free"),
        api_key=os.getenv("LLM_API_KEY"),
        url=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        model_config_dict={"temperature": 0.0},
    )


def _ask_llm(prompt: str) -> str:
    from camel.agents import ChatAgent
    from camel.messages import BaseMessage

    agent = ChatAgent(
        model=_create_model(),
        system_message="You classify Reddit comments. Return ONLY valid JSON.",
    )
    msg = BaseMessage.make_user_message(role_name="User", content=prompt)
    response = agent.step(msg)
    return response.msgs[0].content


def _parse_llm_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def classify_comments(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not comments:
        return []

    comment_block = "\n".join(
        f"[ID={c['comment_id']}] [{c.get('archetype', 'User')}] {c['content']}"
        for c in comments
    )

    prompt = f"""Classify each Reddit comment below. Return ONLY valid JSON matching this schema exactly:

{{
  "comments": [
    {{
      "comment_id": <int>,
      "sentiment": "positive" | "negative" | "neutral",
      "topics": [<short topic strings, max 3>],
      "is_objection": true | false,
      "is_feature_request": true | false,
      "feature_requested": "<feature name>" | null
    }}
  ]
}}

Rules:
- sentiment: based on tone toward the product/post
- topics: 1-3 short labels (e.g. "pricing", "privacy", "competition", "validation")
- is_objection: true if the comment raises a concern or challenge
- is_feature_request: true ONLY if the comment explicitly asks for a missing feature
- feature_requested: the specific feature name, or null

Comments:
{comment_block}"""

    raw = _ask_llm(prompt)
    parsed = _parse_llm_json(raw)
    return parsed.get("comments", [])
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd simulation && python -m pytest tests/test_scorecard.py -v -k "parse_llm or classify"`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_scorecard.py tests/test_scorecard.py
git commit -m "feat(scorecard): add LLM comment classification with JSON parsing"
```

---

### Task 3: Scorecard Builder + Grade Computation

**Files:**
- Modify: `scripts/generate_scorecard.py`
- Modify: `tests/test_scorecard.py`

- [ ] **Step 1: Add tests for `build_scorecard` and `compute_grade`**

Append to `tests/test_scorecard.py`:

```python
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
        "Skeptical PM": {"total": 1, "commented": 1, "liked": 0, "disliked": 1, "silent_count": 0, "silent": False},
        "Early Founder": {"total": 1, "commented": 1, "liked": 1, "disliked": 0, "silent_count": 0, "silent": False},
        "Lurker": {"total": 1, "commented": 0, "liked": 0, "disliked": 0, "silent_count": 1, "silent": True},
    }
    classifications = [
        {"comment_id": 1, "sentiment": "negative", "topics": ["pricing"], "is_objection": True, "is_feature_request": False, "feature_requested": None},
        {"comment_id": 2, "sentiment": "positive", "topics": ["privacy"], "is_objection": False, "is_feature_request": False, "feature_requested": None},
        {"comment_id": 3, "sentiment": "neutral", "topics": ["integration"], "is_objection": False, "is_feature_request": True, "feature_requested": "Slack integration"},
        {"comment_id": 4, "sentiment": "positive", "topics": ["ux", "check-ins"], "is_objection": False, "is_feature_request": False, "feature_requested": None},
    ]
    comment_archetypes = {1: "Skeptical PM", 2: "Early Founder", 3: "Indie Hacker", 4: "HR/People Ops"}

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
        "post_score": 0, "num_likes": 0, "num_dislikes": 0,
        "comment_count": 0, "total_agents": 3, "engaged_agents": 0,
        "silent_agents": 3, "engagement_rate": 0.0,
    }
    participation = {
        "Lurker": {"total": 3, "commented": 0, "liked": 0, "disliked": 0, "silent_count": 3, "silent": True},
    }

    sc = build_scorecard(metrics, participation, [], {})
    assert sc["grade"] in ("D", "F")
    assert sc["themes"] == []
    assert sc["strengths"] == []
    assert sc["problems"] == []
    assert sc["missing_features"] == []
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd simulation && python -m pytest tests/test_scorecard.py -v -k "compute_grade or build_scorecard"`
Expected: FAIL

- [ ] **Step 3: Implement build_scorecard and compute_grade**

Append to `scripts/generate_scorecard.py`:

```python
def compute_grade(
    supportive_pct: float,
    engagement_rate: float,
    likes: int,
    dislikes: int,
    silent_agent_pct: float,
) -> tuple[str, float]:
    like_ratio = likes / (likes + dislikes + 1) * 100
    raw = (
        0.4 * supportive_pct
        + 0.3 * engagement_rate
        + 0.2 * like_ratio
        + 0.1 * (100 - silent_agent_pct)
    )
    score = round(min(100.0, max(0.0, raw)), 1)

    if score > 90:
        letter = "A+"
    elif score > 80:
        letter = "A"
    elif score > 70:
        letter = "B+"
    elif score > 60:
        letter = "B"
    elif score > 50:
        letter = "C+"
    elif score > 40:
        letter = "C"
    elif score > 30:
        letter = "D"
    else:
        letter = "F"

    return letter, score


def build_scorecard(
    metrics: dict[str, Any],
    participation: dict[str, dict[str, Any]],
    classifications: list[dict[str, Any]],
    comment_archetypes: dict[int, str],
) -> dict[str, Any]:
    # --- Archetype x Sentiment matrix ---
    matrix: dict[str, dict[str, int]] = {}
    for arch, data in participation.items():
        matrix[arch] = {"positive": 0, "neutral": 0, "negative": 0, "silent": data["silent_count"]}

    for c in classifications:
        arch = comment_archetypes.get(c.get("comment_id", -1), "Other")
        sentiment = c.get("sentiment", "neutral")
        if arch not in matrix:
            matrix[arch] = {"positive": 0, "neutral": 0, "negative": 0, "silent": 0}
        if sentiment in matrix[arch]:
            matrix[arch][sentiment] += 1

    # --- Top themes by frequency ---
    topic_counts: dict[str, int] = {}
    topic_sentiment: dict[str, dict[str, int]] = {}
    for c in classifications:
        sentiment = c.get("sentiment", "neutral")
        for topic in c.get("topics", []):
            t = topic.lower().strip()
            topic_counts[t] = topic_counts.get(t, 0) + 1
            if t not in topic_sentiment:
                topic_sentiment[t] = {"positive": 0, "negative": 0, "neutral": 0}
            topic_sentiment[t][sentiment] = topic_sentiment[t].get(sentiment, 0) + 1

    sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    themes = []
    for topic, count in sorted_topics:
        ts = topic_sentiment.get(topic, {})
        dominant = max(ts, key=ts.get) if ts else "neutral"
        themes.append({"name": topic, "count": count, "sentiment": dominant})

    # --- Strengths (positive topics) ---
    positive_topics: dict[str, int] = {}
    for c in classifications:
        if c.get("sentiment") == "positive":
            for topic in c.get("topics", []):
                t = topic.lower().strip()
                positive_topics[t] = positive_topics.get(t, 0) + 1
    strengths = [
        {"name": t, "count": n}
        for t, n in sorted(positive_topics.items(), key=lambda x: x[1], reverse=True)[:3]
    ]

    # --- Problems (objections by topic) ---
    objection_topics: dict[str, int] = {}
    for c in classifications:
        if c.get("is_objection"):
            for topic in c.get("topics", []):
                t = topic.lower().strip()
                objection_topics[t] = objection_topics.get(t, 0) + 1
    problems = [
        {"name": t, "count": n}
        for t, n in sorted(objection_topics.items(), key=lambda x: x[1], reverse=True)[:3]
    ]

    # --- Missing features ---
    feature_counts: dict[str, int] = {}
    for c in classifications:
        if c.get("is_feature_request") and c.get("feature_requested"):
            name = c["feature_requested"].strip()
            feature_counts[name] = feature_counts.get(name, 0) + 1
    missing_features = [
        {"name": f, "count": n}
        for f, n in sorted(feature_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    # --- Grade ---
    total_classified = len(classifications) or 1
    supportive_pct = sum(
        1 for c in classifications if c.get("sentiment") == "positive"
    ) / total_classified * 100
    silent_agent_pct = (
        metrics["silent_agents"] / metrics["total_agents"] * 100
        if metrics["total_agents"]
        else 100.0
    )

    letter, score = compute_grade(
        supportive_pct=supportive_pct,
        engagement_rate=metrics["engagement_rate"],
        likes=metrics["num_likes"],
        dislikes=metrics["num_dislikes"],
        silent_agent_pct=silent_agent_pct,
    )

    return {
        "grade": letter,
        "score": round(score / 10, 1),
        "summary": (
            f"Based on: {metrics['num_likes']} likes, {metrics['num_dislikes']} dislikes, "
            f"{metrics['engagement_rate']}% engagement"
        ),
        "matrix": matrix,
        "themes": themes,
        "strengths": strengths,
        "problems": problems,
        "missing_features": missing_features,
        "metrics": metrics,
    }
```

- [ ] **Step 4: Run all scorecard tests**

Run: `cd simulation && python -m pytest tests/test_scorecard.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_scorecard.py tests/test_scorecard.py
git commit -m "feat(scorecard): add build_scorecard and compute_grade with merge logic"
```

---

### Task 4: Top-Level Orchestrator + Comment Fetching

**Files:**
- Modify: `scripts/generate_scorecard.py`
- Modify: `tests/test_scorecard.py`

- [ ] **Step 1: Add test for `generate_scorecard` orchestrator**

Append to `tests/test_scorecard.py`:

```python
def test_generate_scorecard_full(test_db, profiles_path, monkeypatch):
    from scripts import generate_scorecard

    fake_response = json.dumps({
        "comments": [
            {"comment_id": 1, "sentiment": "negative", "topics": ["pricing"], "is_objection": True, "is_feature_request": False, "feature_requested": None},
            {"comment_id": 2, "sentiment": "positive", "topics": ["privacy"], "is_objection": False, "is_feature_request": False, "feature_requested": None},
            {"comment_id": 3, "sentiment": "neutral", "topics": ["integration"], "is_objection": False, "is_feature_request": True, "feature_requested": "Slack integration"},
            {"comment_id": 4, "sentiment": "positive", "topics": ["ux"], "is_objection": False, "is_feature_request": False, "feature_requested": None},
        ]
    })
    monkeypatch.setattr(generate_scorecard, "_ask_llm", lambda prompt: fake_response)

    sc = generate_scorecard.generate_scorecard(test_db, profiles_path)

    assert sc["grade"] in ("A+", "A", "B+", "B", "C+", "C", "D", "F")
    assert isinstance(sc["score"], float)
    assert len(sc["matrix"]) > 0
    assert sc["metrics"]["comment_count"] == 4
```

- [ ] **Step 2: Implement orchestrator**

Append to `scripts/generate_scorecard.py`:

```python
def fetch_comments_with_archetypes(
    db_path: str, profiles_path: str
) -> tuple[list[dict[str, Any]], dict[int, str]]:
    with open(profiles_path) as f:
        profiles = json.load(f)

    name_to_archetype: dict[str, str] = {}
    for p in profiles:
        name_to_archetype[p["username"]] = _archetype_for(p["username"])

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT c.comment_id, c.content, COALESCE(u.user_name, u.name) as author, u.user_id "
        "FROM comment c JOIN user u ON c.user_id = u.user_id "
        "WHERE c.post_id = 1 ORDER BY c.created_at"
    )
    comments = []
    comment_archetypes: dict[int, str] = {}
    for cid, content, author, uid in cur.fetchall():
        archetype = name_to_archetype.get(author, _archetype_for(author))
        comments.append({
            "comment_id": cid,
            "content": content,
            "author": author,
            "archetype": archetype,
        })
        comment_archetypes[cid] = archetype

    conn.close()
    return comments, comment_archetypes


def generate_scorecard(db_path: str, profiles_path: str) -> dict[str, Any]:
    metrics = query_engagement_metrics(db_path)
    participation = query_archetype_participation(db_path, profiles_path)
    comments, comment_archetypes = fetch_comments_with_archetypes(db_path, profiles_path)
    classifications = classify_comments(comments)
    return build_scorecard(metrics, participation, classifications, comment_archetypes)
```

- [ ] **Step 3: Run all tests**

Run: `cd simulation && python -m pytest tests/test_scorecard.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/generate_scorecard.py tests/test_scorecard.py
git commit -m "feat(scorecard): add top-level generate_scorecard orchestrator"
```

---

### Task 5: Server Endpoints

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Add scorecard import and endpoint**

At top of `server.py`, add import:

```python
import scripts.generate_scorecard as scorecard_module
```

Replace the existing `/api/analyze/{tag}` endpoint (the `_apply_llm_config`, `_restore_env`, and `analyze_tag` function block) with:

```python
def _apply_llm_config(config: LLMConfig) -> dict[str, str]:
    originals: dict[str, str] = {}
    mapping = {
        "LLM_API_KEY": config.llm_api_key,
        "LLM_BASE_URL": config.llm_base_url,
        "LLM_MODEL": config.llm_model,
    }
    for key, value in mapping.items():
        if value:
            originals[key] = os.environ.get(key, "")
            os.environ[key] = value
    return originals


def _restore_env(originals: dict[str, str]) -> None:
    for key, value in originals.items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)


@app.post("/api/scorecard/{tag}")
async def get_scorecard(tag: str):
    db_path = RESULTS_DIR / f"{tag}.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"Results not found for tag '{tag}'")

    profiles_path = resolve_profiles_for_tag(tag)
    saved = _apply_llm_config(coordinator._llm_config)
    try:
        result = await asyncio.to_thread(
            scorecard_module.generate_scorecard, str(db_path), str(profiles_path)
        )
    finally:
        _restore_env(saved)

    return JSONResponse(content=result)


@app.post("/api/rewrite/{tag}")
async def rewrite_post_endpoint(tag: str) -> dict[str, str]:
    db_path = RESULTS_DIR / f"{tag}.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"Results not found for tag '{tag}'")

    saved = _apply_llm_config(coordinator._llm_config)
    try:
        original_post = await asyncio.to_thread(fetch_original_post, str(db_path))
        profiles_path = resolve_profiles_for_tag(tag)
        scorecard = await asyncio.to_thread(
            scorecard_module.generate_scorecard, str(db_path), str(profiles_path)
        )
        analysis_context = json.dumps(scorecard, indent=2, default=str)
        improved_post = await asyncio.to_thread(rewrite_post, original_post, analysis_context)
    finally:
        _restore_env(saved)

    return {"improved_post": improved_post}
```

Keep the old `/api/analyze/{tag}` endpoint too for backward compat but it can be removed later.

- [ ] **Step 2: Verify server starts**

Run: `cd simulation && python -c "from server import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "feat(scorecard): add /api/scorecard and /api/rewrite endpoints"
```

---

### Task 6: Replace Analysis Tab UI with Scorecard Cards

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: Replace Analysis tab HTML**

In `static/index.html`, replace the entire `tab-analysis` div content (the section containing `analyze-btn`, `analysis-content`, `analysis-markdown`, `improved-post`, `resimulate-btn`) with:

```html
<div id="tab-analysis" class="tab-content">
  <button id="analyze-btn" style="margin-bottom: 20px;">📊 Generate Scorecard</button>

  <div id="scorecard" class="hidden">
    <!-- Reception Header -->
    <div class="scorecard-header" id="sc-header">
      <div class="grade-circle" id="sc-grade">?</div>
      <div class="grade-detail">
        <div class="grade-score" id="sc-score">0/10</div>
        <div class="grade-summary" id="sc-summary">Run analysis to see results</div>
      </div>
    </div>

    <!-- Archetype x Sentiment Matrix -->
    <div class="scorecard-section">
      <h3>Archetype Breakdown</h3>
      <table class="matrix-table" id="sc-matrix">
        <thead><tr><th></th><th>👍</th><th>😐</th><th>👎</th><th>🔇</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>

    <!-- Top Themes -->
    <div class="scorecard-section">
      <h3>Top Themes</h3>
      <div id="sc-themes"></div>
    </div>

    <!-- Strengths & Problems -->
    <div class="scorecard-section sc-two-col">
      <div>
        <h3>✅ Strengths</h3>
        <ul id="sc-strengths"></ul>
      </div>
      <div>
        <h3>❌ Problems</h3>
        <ul id="sc-problems"></ul>
      </div>
    </div>

    <!-- Missing Features -->
    <div class="scorecard-section hidden" id="sc-features-section">
      <h3>🔍 Missing Features</h3>
      <ul id="sc-features"></ul>
    </div>

    <!-- Rewrite -->
    <div class="scorecard-section" style="margin-top: 24px;">
      <button id="rewrite-btn">🔄 Rewrite Post Based on Feedback</button>
      <div id="rewrite-result" class="hidden" style="margin-top: 16px;">
        <h3>Improved Post</h3>
        <textarea id="improved-post" readonly style="height: 200px;"></textarea>
        <button id="resimulate-btn" style="margin-top: 12px; background: var(--border);">🔄 Re-simulate with this post</button>
      </div>
    </div>
  </div>
</div>
```

- [ ] **Step 2: Add scorecard CSS**

Add before the closing `</style>` tag:

```css
.scorecard-header {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 20px;
  background: var(--bg);
  border-radius: 8px;
  margin-bottom: 20px;
}
.grade-circle {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  font-weight: 800;
  color: #fff;
  background: var(--border);
  flex-shrink: 0;
}
.grade-circle.green { background: #2e7d32; }
.grade-circle.yellow { background: #f9a825; color: #000; }
.grade-circle.red { background: #c62828; }
.grade-detail { flex: 1; }
.grade-score { font-size: 20px; font-weight: 700; color: #fff; }
.grade-summary { font-size: 13px; color: var(--muted); margin-top: 4px; }

.scorecard-section {
  background: var(--bg);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.scorecard-section h3 { font-size: 14px; font-weight: 700; color: #fff; margin-bottom: 12px; }

.sc-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 600px) { .sc-two-col { grid-template-columns: 1fr; } }

.matrix-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.matrix-table th { text-align: center; padding: 8px; color: var(--muted); font-weight: 600; }
.matrix-table th:first-child { text-align: left; }
.matrix-table td { text-align: center; padding: 8px; border-top: 1px solid var(--border); }
.matrix-table td:first-child { text-align: left; font-weight: 600; color: var(--text); }
.matrix-table td.silent { color: var(--muted); font-style: italic; }

.theme-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 13px; }
.theme-bar .bar { height: 8px; border-radius: 4px; min-width: 20px; }
.theme-bar .bar.positive { background: var(--success); }
.theme-bar .bar.negative { background: var(--error); }
.theme-bar .bar.neutral { background: var(--muted); }
.theme-bar .count { color: var(--muted); font-size: 12px; min-width: 24px; }

.scorecard-section ul { list-style: none; }
.scorecard-section li { font-size: 13px; padding: 4px 0; color: var(--text); }
.scorecard-section li .freq { color: var(--muted); margin-left: 4px; }
```

- [ ] **Step 3: Replace Analysis tab JS**

Replace the existing analyze button click handler and related code (the `analyzeBtn.addEventListener` block, plus `resimulateBtn.addEventListener`) with:

```javascript
const analyzeBtn = document.getElementById('analyze-btn');
const scorecard = document.getElementById('scorecard');
const rewriteBtn = document.getElementById('rewrite-btn');
const rewriteResult = document.getElementById('rewrite-result');
const improvedPost = document.getElementById('improved-post');
const resimulateBtn = document.getElementById('resimulate-btn');

analyzeBtn.addEventListener('click', async () => {
  analyzeBtn.disabled = true;
  analyzeBtn.innerHTML = '<span class="spinner"></span> Analyzing...';

  try {
    const data = await fetch('/api/scorecard/run', {method: 'POST'}).then(r => r.json());
    analyzeBtn.style.display = 'none';
    scorecard.classList.remove('hidden');
    renderScorecard(data);
  } catch (err) {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = '📊 Generate Scorecard';
    alert('Analysis failed: ' + err.message);
  }
});

function renderScorecard(data) {
  // Grade header
  const gradeEl = document.getElementById('sc-grade');
  gradeEl.textContent = data.grade;
  gradeEl.className = 'grade-circle';
  if (['A+', 'A', 'B+', 'B'].includes(data.grade)) gradeEl.classList.add('green');
  else if (['C+', 'C'].includes(data.grade)) gradeEl.classList.add('yellow');
  else gradeEl.classList.add('red');

  document.getElementById('sc-score').textContent = data.score + '/10';
  document.getElementById('sc-summary').textContent = data.summary;

  // Matrix
  const tbody = document.querySelector('#sc-matrix tbody');
  tbody.innerHTML = '';
  for (const [arch, counts] of Object.entries(data.matrix)) {
    const row = document.createElement('tr');
    const silent = counts.silent || 0;
    row.innerHTML = `
      <td>${arch}</td>
      <td>${counts.positive || 0}</td>
      <td>${counts.neutral || 0}</td>
      <td>${counts.negative || 0}</td>
      <td class="silent">${silent > 0 ? silent : ''}</td>
    `;
    tbody.appendChild(row);
  }

  // Themes
  const themesEl = document.getElementById('sc-themes');
  themesEl.innerHTML = '';
  const maxCount = data.themes.length ? Math.max(...data.themes.map(t => t.count)) : 1;
  data.themes.forEach(t => {
    const pct = Math.round((t.count / maxCount) * 100);
    themesEl.innerHTML += `
      <div class="theme-bar">
        <span style="min-width:120px">${t.name}</span>
        <div class="bar ${t.sentiment}" style="width:${pct}%"></div>
        <span class="count">${t.count}×</span>
      </div>
    `;
  });

  // Strengths
  const strengthsEl = document.getElementById('sc-strengths');
  strengthsEl.innerHTML = '';
  data.strengths.forEach(s => {
    strengthsEl.innerHTML += `<li>• ${s.name} <span class="freq">(${s.count}×)</span></li>`;
  });
  if (!data.strengths.length) strengthsEl.innerHTML = '<li style="color:var(--muted)">None detected</li>';

  // Problems
  const problemsEl = document.getElementById('sc-problems');
  problemsEl.innerHTML = '';
  data.problems.forEach(p => {
    problemsEl.innerHTML += `<li>• ${p.name} <span class="freq">(${p.count}×)</span></li>`;
  });
  if (!data.problems.length) problemsEl.innerHTML = '<li style="color:var(--muted)">None detected</li>';

  // Missing features
  const featSection = document.getElementById('sc-features-section');
  const featEl = document.getElementById('sc-features');
  featEl.innerHTML = '';
  if (data.missing_features.length) {
    featSection.classList.remove('hidden');
    data.missing_features.forEach(f => {
      featEl.innerHTML += `<li>• ${f.name} <span class="freq">(${f.count}×)</span></li>`;
    });
  }
}

rewriteBtn.addEventListener('click', async () => {
  rewriteBtn.disabled = true;
  rewriteBtn.innerHTML = '<span class="spinner"></span> Rewriting...';

  try {
    const data = await fetch('/api/rewrite/run', {method: 'POST'}).then(r => r.json());
    rewriteResult.classList.remove('hidden');
    improvedPost.value = data.improved_post || '';
    rewriteBtn.style.display = 'none';
  } catch (err) {
    rewriteBtn.disabled = false;
    rewriteBtn.textContent = '🔄 Rewrite Post Based on Feedback';
    alert('Rewrite failed: ' + err.message);
  }
});

resimulateBtn.addEventListener('click', () => {
  postContent.value = improvedPost.value;
  window.scrollTo({top: 0, behavior: 'smooth'});
  tabs[0].click();
  launchBtn.click();
});
```

- [ ] **Step 4: Remove old analysis-specific code**

Remove from JS:
- The old `analysisContent`, `analysisMarkdown` element references
- The old `renderSimpleMarkdown` function (no longer needed)

- [ ] **Step 5: Verify page loads without JS errors**

Open browser to `http://localhost:8000`, open DevTools console.
Expected: No JS errors, scorecard tab shows "📊 Generate Scorecard" button.

- [ ] **Step 6: Commit**

```bash
git add static/index.html
git commit -m "feat(scorecard): replace Analysis tab with structured scorecard UI"
```

---

### Task 7: Integration Verification

**Files:** None (testing only)

- [ ] **Step 1: Run full test suite**

Run: `cd simulation && python -m pytest tests/ -v`
Expected: ALL existing tests pass + all new scorecard tests pass

- [ ] **Step 2: Restart server and verify UI loads**

Kill existing server, restart:
```bash
cd simulation && python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`:
- Config panel shows sliders + LLM settings
- Thread tab renders (if previous simulation exists)
- Analysis tab shows "📊 Generate Scorecard" button

- [ ] **Step 3: Commit all remaining changes**

```bash
git add -A
git commit -m "feat(scorecard): complete scorecard feature — analysis, UI, endpoints"
```
