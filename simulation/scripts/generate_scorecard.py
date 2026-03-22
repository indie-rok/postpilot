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
        is_engaged = (
            bool(meaningful) or uid in commenters or uid in likers or uid in dislikers
        )

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
    matrix: dict[str, dict[str, int]] = {}
    for arch, data in participation.items():
        matrix[arch] = {
            "positive": 0,
            "neutral": 0,
            "negative": 0,
            "silent": data["silent_count"],
        }

    for c in classifications:
        arch = comment_archetypes.get(c.get("comment_id", -1), "Other")
        sentiment = c.get("sentiment", "neutral")
        if arch not in matrix:
            matrix[arch] = {"positive": 0, "neutral": 0, "negative": 0, "silent": 0}
        if sentiment in matrix[arch]:
            matrix[arch][sentiment] += 1

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

    positive_topics: dict[str, int] = {}
    for c in classifications:
        if c.get("sentiment") == "positive":
            for topic in c.get("topics", []):
                t = topic.lower().strip()
                positive_topics[t] = positive_topics.get(t, 0) + 1
    strengths = [
        {"name": t, "count": n}
        for t, n in sorted(positive_topics.items(), key=lambda x: x[1], reverse=True)[
            :3
        ]
    ]

    objection_topics: dict[str, int] = {}
    for c in classifications:
        if c.get("is_objection"):
            for topic in c.get("topics", []):
                t = topic.lower().strip()
                objection_topics[t] = objection_topics.get(t, 0) + 1
    problems = [
        {"name": t, "count": n}
        for t, n in sorted(objection_topics.items(), key=lambda x: x[1], reverse=True)[
            :3
        ]
    ]

    feature_counts: dict[str, int] = {}
    for c in classifications:
        if c.get("is_feature_request") and c.get("feature_requested"):
            name = c["feature_requested"].strip()
            feature_counts[name] = feature_counts.get(name, 0) + 1
    missing_features = [
        {"name": f, "count": n}
        for f, n in sorted(feature_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    total_classified = len(classifications) or 1
    supportive_pct = (
        sum(1 for c in classifications if c.get("sentiment") == "positive")
        / total_classified
        * 100
    )
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
        comments.append(
            {
                "comment_id": cid,
                "content": content,
                "author": author,
                "archetype": archetype,
            }
        )
        comment_archetypes[cid] = archetype

    conn.close()
    return comments, comment_archetypes


def generate_scorecard(db_path: str, profiles_path: str) -> dict[str, Any]:
    metrics = query_engagement_metrics(db_path)
    participation = query_archetype_participation(db_path, profiles_path)
    comments, comment_archetypes = fetch_comments_with_archetypes(
        db_path, profiles_path
    )
    classifications = classify_comments(comments)
    return build_scorecard(metrics, participation, classifications, comment_archetypes)
