# pyright: reportMissingImports=false, reportImplicitRelativeImport=false

from __future__ import annotations

import json
import os
import sqlite3
import sys
from typing import Any

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db import save_scorecard


def query_engagement_metrics(app_db_path: str, run_id: int) -> dict[str, Any]:
    conn = sqlite3.connect(app_db_path)
    cur = conn.cursor()

    cur.execute("SELECT post_likes, post_dislikes FROM run WHERE id = ?", (run_id,))
    num_likes, num_dislikes = cur.fetchone()

    cur.execute("SELECT COUNT(*) FROM run_comment WHERE run_id = ?", (run_id,))
    comment_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM run_agent WHERE run_id = ?", (run_id,))
    total_agents = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM run_agent WHERE run_id = ? AND engaged = 1", (run_id,)
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
    app_db_path: str, run_id: int
) -> dict[str, dict[str, Any]]:
    conn = sqlite3.connect(app_db_path)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            a.archetype,
            a.engaged,
            (
                SELECT COUNT(*)
                FROM run_comment c
                WHERE c.agent_id = a.id
            ) AS comment_count
        FROM run_agent a
        WHERE a.run_id = ?
        """,
        (run_id,),
    )
    rows = cur.fetchall()

    conn.close()

    result: dict[str, dict[str, Any]] = {}

    for archetype, engaged, comment_count in rows:
        arch = archetype or "Other"
        commented = (comment_count or 0) > 0
        if arch not in result:
            result[arch] = {
                "total": 0,
                "commented": 0,
                "silent_count": 0,
                "silent": False,
            }
        entry = result[arch]
        entry["total"] += 1

        if commented:
            entry["commented"] += 1
        if not engaged:
            entry["silent_count"] += 1

    for entry in result.values():
        entry["silent"] = entry["silent_count"] == entry["total"]

    return result


def query_engagement_timeline(app_db_path: str, run_id: int) -> list[dict[str, Any]]:
    conn = sqlite3.connect(app_db_path)
    cur = conn.cursor()

    cur.execute("SELECT MIN(created_at) FROM run_comment WHERE run_id = ?", (run_id,))
    first_row = cur.fetchone()
    if not first_row or not first_row[0]:
        conn.close()
        return []

    cur.execute(
        "SELECT "
        "  CAST((julianday(created_at) - julianday(?)) * 24 AS INTEGER) AS hour_offset, "
        "  COUNT(*) AS cnt "
        "FROM run_comment WHERE run_id = ? "
        "GROUP BY hour_offset ORDER BY hour_offset",
        (first_row[0], run_id),
    )
    timeline = [{"hour": row[0], "comments": row[1]} for row in cur.fetchall()]
    conn.close()
    return timeline


def query_engagement_depth(app_db_path: str, run_id: int) -> dict[str, dict[str, Any]]:
    conn = sqlite3.connect(app_db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT a.archetype, LENGTH(c.content) "
        "FROM run_comment c JOIN run_agent a ON c.agent_id = a.id "
        "WHERE c.run_id = ?",
        (run_id,),
    )
    arch_lengths: dict[str, list[int]] = {}
    for archetype, length in cur.fetchall():
        arch = archetype or "Other"
        arch_lengths.setdefault(arch, []).append(length or 0)

    conn.close()

    result: dict[str, dict[str, Any]] = {}
    for arch, lengths in arch_lengths.items():
        result[arch] = {
            "avg_length": round(sum(lengths) / len(lengths)) if lengths else 0,
            "comment_count": len(lengths),
        }
    return result


def _create_model():
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType

    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=os.getenv("LLM_MODEL", "gpt-5-mini"),
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


DEFAULT_BATCH_SIZE = 5


def _classify_batch(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    comment_block = "\n".join(
        f"[ID={c['comment_id']}] [{c.get('archetype', 'User')}] {c['content'][:300]}"
        for c in batch
    )

    prompt = f"""Classify each Reddit comment. Return ONLY valid JSON:

{{
  "comments": [
    {{
      "comment_id": <int>,
      "sentiment": "positive" | "negative" | "neutral",
      "topics": ["<descriptive 3-6 word phrase>"],
      "is_objection": true | false,
      "is_feature_request": true | false,
      "feature_requested": "<feature name>" | null,
      "objection_type": "trust" | "value" | "technical" | "pricing" | null,
      "would_click_link": "yes" | "likely" | "unlikely" | "no",
      "would_signup": "yes" | "likely" | "unlikely" | "no",
      "understands_product": "yes" | "partially" | "no",
      "would_recommend": "yes" | "maybe" | "no",
      "is_question": true | false,
      "mentions_competitor": true | false,
      "competitor_name": "<name>" | null,
      "mentions_pricing": true | false
    }}
  ]
}}

IMPORTANT: topics must be descriptive phrases, NOT single words.
Good: "burnout radar approach praised", "pricing too high for startups"
Bad: "pricing", "burnout", "privacy"

Field guidance:
- objection_type: categorize the objection (trust=credibility/data concerns, value=why not use X, technical=integration/architecture, pricing=cost). null if not an objection.
- would_click_link: based on tone and interest level, would this person click a link to try the app?
- would_signup: would they actually create an account? (stricter than clicking)
- understands_product: does the comment show they grasp what the product does?
- would_recommend: would they tell a colleague about this?
- is_question: is the comment primarily asking a question?
- mentions_competitor: does the comment name a competing product?
- mentions_pricing: does the comment discuss pricing, cost, or budget?

Comments:
{comment_block}"""

    raw = _ask_llm(prompt)
    parsed = _parse_llm_json(raw)
    return parsed.get("comments", [])


def classify_comments(
    comments: list[dict[str, Any]], batch_size: int = 0
) -> list[dict[str, Any]]:
    if not comments:
        return []

    effective_batch = len(comments) if batch_size <= 0 else batch_size
    all_results: list[dict[str, Any]] = []
    classified_ids: set[int] = set()
    for i in range(0, len(comments), effective_batch):
        batch = comments[i : i + effective_batch]
        batch_results = _classify_batch(batch)
        for r in batch_results:
            classified_ids.add(r.get("comment_id", -1))
        all_results.extend(batch_results)

    for c in comments:
        if c["comment_id"] not in classified_ids:
            all_results.append(
                {
                    "comment_id": c["comment_id"],
                    "sentiment": "neutral",
                    "topics": [],
                    "is_objection": False,
                    "is_feature_request": False,
                    "feature_requested": None,
                    "objection_type": None,
                    "would_click_link": "unlikely",
                    "would_signup": "unlikely",
                    "understands_product": "partially",
                    "would_recommend": "maybe",
                    "is_question": False,
                    "mentions_competitor": False,
                    "competitor_name": None,
                    "mentions_pricing": False,
                }
            )

    return all_results


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


def _pct(count: int, total: int) -> float:
    return round(count / total * 100, 1) if total else 0.0


def _intent_rate(
    classifications: list[dict[str, Any]], field: str, positive_values: set[str]
) -> float:
    total = len(classifications) or 1
    count = sum(1 for c in classifications if c.get(field) in positive_values)
    return _pct(count, total)


def _intent_by_archetype(
    classifications: list[dict[str, Any]],
    comment_archetypes: dict[int, str],
    field: str,
    positive_values: set[str],
) -> dict[str, float]:
    arch_total: dict[str, int] = {}
    arch_positive: dict[str, int] = {}
    for c in classifications:
        arch = comment_archetypes.get(c.get("comment_id", -1), "Other")
        arch_total[arch] = arch_total.get(arch, 0) + 1
        if c.get(field) in positive_values:
            arch_positive[arch] = arch_positive.get(arch, 0) + 1
    return {
        arch: _pct(arch_positive.get(arch, 0), arch_total[arch]) for arch in arch_total
    }


def build_scorecard(
    metrics: dict[str, Any],
    participation: dict[str, dict[str, Any]],
    classifications: list[dict[str, Any]],
    comment_archetypes: dict[int, str],
    comments: list[dict[str, Any]] | None = None,
    engagement_timeline: list[dict[str, Any]] | None = None,
    engagement_depth: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    comment_text_by_id: dict[int, str] = {}
    comment_author_by_id: dict[int, str] = {}
    comment_archetype_by_id: dict[int, str] = {}
    if comments:
        for c in comments:
            comment_text_by_id[c["comment_id"]] = c["content"]
            comment_author_by_id[c["comment_id"]] = c.get("author", "agent")
            comment_archetype_by_id[c["comment_id"]] = c.get("archetype", "Other")

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
        dominant = max(ts, key=lambda k: ts.get(k, 0)) if ts else "neutral"
        themes.append({"name": topic, "count": count, "sentiment": dominant})

    positive_topics: dict[str, int] = {}
    positive_quotes: dict[str, list[str]] = {}
    for c in classifications:
        if c.get("sentiment") == "positive":
            cid = c.get("comment_id", -1)
            quote = comment_text_by_id.get(cid, "")
            author = comment_author_by_id.get(cid, "agent")
            for topic in c.get("topics", []):
                t = topic.lower().strip()
                positive_topics[t] = positive_topics.get(t, 0) + 1
                if quote and t not in positive_quotes:
                    positive_quotes[t] = []
                if quote:
                    positive_quotes[t].append(f"{author}: {quote}")
    strengths = [
        {"name": t, "count": n, "quotes": positive_quotes.get(t, [])[:2]}
        for t, n in sorted(positive_topics.items(), key=lambda x: x[1], reverse=True)[
            :3
        ]
    ]

    objection_topics: dict[str, int] = {}
    objection_quotes: dict[str, list[str]] = {}
    for c in classifications:
        if c.get("is_objection"):
            cid = c.get("comment_id", -1)
            quote = comment_text_by_id.get(cid, "")
            author = comment_author_by_id.get(cid, "agent")
            for topic in c.get("topics", []):
                t = topic.lower().strip()
                objection_topics[t] = objection_topics.get(t, 0) + 1
                if quote and t not in objection_quotes:
                    objection_quotes[t] = []
                if quote:
                    objection_quotes[t].append(f"{author}: {quote}")
    problems = [
        {"name": t, "count": n, "quotes": objection_quotes.get(t, [])[:2]}
        for t, n in sorted(objection_topics.items(), key=lambda x: x[1], reverse=True)[
            :3
        ]
    ]

    feature_counts: dict[str, int] = {}
    feature_quotes: dict[str, list[str]] = {}
    for c in classifications:
        if c.get("is_feature_request") and c.get("feature_requested"):
            name = c["feature_requested"].strip()
            feature_counts[name] = feature_counts.get(name, 0) + 1
            cid = c.get("comment_id", -1)
            quote = comment_text_by_id.get(cid, "")
            author = comment_author_by_id.get(cid, "agent")
            if quote:
                feature_quotes.setdefault(name, []).append(f"{author}: {quote}")
    missing_features = [
        {"name": f, "count": n, "quotes": feature_quotes.get(f, [])[:2]}
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

    total_agents = metrics["total_agents"] or 1
    click_positive = {"yes", "likely"}
    click_count = sum(
        1 for c in classifications if c.get("would_click_link") in click_positive
    )
    click_through = {
        "count": click_count,
        "total": total_agents,
        "rate": _pct(click_count, total_agents),
        "by_archetype": _intent_by_archetype(
            classifications, comment_archetypes, "would_click_link", click_positive
        ),
    }

    signup_positive = {"yes", "likely"}
    signup_count = sum(
        1 for c in classifications if c.get("would_signup") in signup_positive
    )
    signup_funnel = {
        "would_click_count": click_count,
        "would_signup_count": signup_count,
        "total": total_agents,
        "would_click_pct": _pct(click_count, total_agents),
        "would_signup_pct": _pct(signup_count, total_agents),
        "by_archetype": _intent_by_archetype(
            classifications, comment_archetypes, "would_signup", signup_positive
        ),
    }

    clear_count = sum(
        1 for c in classifications if c.get("understands_product") == "yes"
    )
    partial_count = sum(
        1 for c in classifications if c.get("understands_product") == "partially"
    )
    confused_count = sum(
        1 for c in classifications if c.get("understands_product") == "no"
    )
    message_clarity = {
        "score": _pct(clear_count, total_classified),
        "clear": clear_count,
        "partial": partial_count,
        "confused": confused_count,
    }

    objection_type_comments: dict[str, dict[int, dict[str, str]]] = {}
    for c in classifications:
        otype = c.get("objection_type")
        if otype and c.get("is_objection"):
            cid = c.get("comment_id", -1)
            if cid not in objection_type_comments.setdefault(otype, {}):
                objection_type_comments[otype][cid] = {
                    "author": comment_author_by_id.get(cid, "agent"),
                    "text": comment_text_by_id.get(cid, ""),
                }
    objection_map = [
        {
            "type": otype,
            "count": len(by_cid),
            "items": list(by_cid.values())[:3],
        }
        for otype, by_cid in sorted(
            objection_type_comments.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )
    ]

    competitor_counts: dict[str, int] = {}
    for c in classifications:
        if c.get("mentions_competitor") and c.get("competitor_name"):
            name = c["competitor_name"].strip()
            if name:
                competitor_counts[name] = competitor_counts.get(name, 0) + 1
    competitive_mentions = [
        {"name": n, "count": cnt}
        for n, cnt in sorted(
            competitor_counts.items(), key=lambda x: x[1], reverse=True
        )
    ]

    question_count = sum(1 for c in classifications if c.get("is_question"))
    question_density = {
        "rate": _pct(question_count, total_classified),
        "count": question_count,
        "total": total_classified,
    }

    pricing_count = sum(1 for c in classifications if c.get("mentions_pricing"))
    pricing_sensitivity = {
        "rate": _pct(pricing_count, total_classified),
        "mentioned": pricing_count,
        "total": total_classified,
    }

    recommend_positive = {"yes", "maybe"}
    word_of_mouth = {
        "rate": _intent_rate(classifications, "would_recommend", recommend_positive),
        "by_archetype": _intent_by_archetype(
            classifications, comment_archetypes, "would_recommend", recommend_positive
        ),
    }

    hook_engaged = sum(
        1
        for c in classifications
        if c.get("understands_product") in ("yes", "partially")
        and c.get("sentiment") != "neutral"
    )
    hook_effectiveness = {
        "engaged_with_problem_pct": _pct(hook_engaged, total_classified),
        "generic_pct": _pct(total_classified - hook_engaged, total_classified),
    }

    audience_fit: list[dict[str, Any]] = []
    for arch, part_data in participation.items():
        arch_comments = [
            c
            for c in classifications
            if comment_archetypes.get(c.get("comment_id", -1)) == arch
        ]
        arch_comment_count = len(arch_comments)
        positive_rate = (
            _pct(
                sum(1 for c in arch_comments if c.get("sentiment") == "positive"),
                arch_comment_count,
            )
            if arch_comment_count
            else 0.0
        )
        depth_info = (engagement_depth or {}).get(arch, {})
        audience_fit.append(
            {
                "archetype": arch,
                "agent_count": part_data["total"],
                "positive_rate": positive_rate,
                "comment_count": arch_comment_count,
                "avg_length": depth_info.get("avg_length", 0),
            }
        )
    audience_fit.sort(key=lambda x: x["positive_rate"], reverse=True)

    sentiment_drift: list[dict[str, Any]] = []
    if engagement_timeline:
        hour_sentiments: dict[int, dict[str, int]] = {}
        comment_hour: dict[int, int] = {}
        if comments:
            sorted_comments = sorted(comments, key=lambda c: c.get("comment_id", 0))
            for i, sc in enumerate(sorted_comments):
                matching_tl = (
                    engagement_timeline[0]["hour"] if engagement_timeline else 0
                )
                for tl in engagement_timeline:
                    if i < tl.get("_cumulative", i + 1):
                        matching_tl = tl["hour"]
                        break
                comment_hour[sc["comment_id"]] = matching_tl

        for c in classifications:
            cid = c.get("comment_id", -1)
            hour = comment_hour.get(cid, 0)
            if hour not in hour_sentiments:
                hour_sentiments[hour] = {"positive": 0, "neutral": 0, "negative": 0}
            sent = c.get("sentiment", "neutral")
            if sent in hour_sentiments[hour]:
                hour_sentiments[hour][sent] += 1

        for hour in sorted(hour_sentiments):
            entry = hour_sentiments[hour]
            entry["hour"] = hour
            sentiment_drift.append(entry)

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
        "click_through": click_through,
        "signup_funnel": signup_funnel,
        "message_clarity": message_clarity,
        "objection_map": objection_map,
        "competitive_mentions": competitive_mentions,
        "question_density": question_density,
        "pricing_sensitivity": pricing_sensitivity,
        "word_of_mouth": word_of_mouth,
        "hook_effectiveness": hook_effectiveness,
        "audience_fit": audience_fit,
        "sentiment_drift": sentiment_drift,
        "engagement_decay": engagement_timeline or [],
        "engagement_depth": engagement_depth or {},
    }


def fetch_comments_with_archetypes(
    app_db_path: str, run_id: int
) -> tuple[list[dict[str, Any]], dict[int, str]]:
    conn = sqlite3.connect(app_db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT c.id, c.content, a.realname, a.archetype "
        "FROM run_comment c JOIN run_agent a ON c.agent_id = a.id "
        "WHERE c.run_id = ? ORDER BY c.created_at",
        (run_id,),
    )
    comments = []
    comment_archetypes: dict[int, str] = {}
    for cid, content, author, archetype in cur.fetchall():
        arch = archetype or "Other"
        comments.append(
            {
                "comment_id": cid,
                "content": content,
                "author": author,
                "archetype": arch,
            }
        )
        comment_archetypes[cid] = arch

    conn.close()
    return comments, comment_archetypes


def _load_archetype_bios(app_db_path: str, run_id: int) -> dict[str, str]:
    conn = sqlite3.connect(app_db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT archetype, bio
        FROM run_agent
        WHERE run_id = ? AND bio IS NOT NULL
        """,
        (run_id,),
    )
    bios: dict[str, str] = {}
    for archetype, bio in cur.fetchall():
        if archetype and bio and archetype not in bios:
            bios[archetype] = bio[:200]
    conn.close()
    return bios


def load_interviews(app_db_path: str, run_id: int) -> list[dict[str, Any]]:
    conn = sqlite3.connect(app_db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ri.response, ri.clarity, ri.would_click, ri.would_signup,
               a.username, a.archetype
        FROM run_interview ri
        JOIN run_agent a ON ri.agent_id = a.id
        WHERE ri.run_id = ?
        """,
        (run_id,),
    )
    interviews = [
        {
            "username": username,
            "archetype": archetype,
            "response": response,
            "clarity": clarity,
            "would_click": would_click,
            "would_signup": would_signup,
            "success": True,
        }
        for response, clarity, would_click, would_signup, username, archetype in cur.fetchall()
    ]
    conn.close()
    return interviews


def _extract_post_summary(app_db_path: str, run_id: int) -> str:
    """Derive a short product summary from the actual post content in the DB."""
    conn = sqlite3.connect(app_db_path)
    cur = conn.cursor()
    cur.execute("SELECT post_content FROM run WHERE id = ?", (run_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        return "Unknown product"
    content = row[0].strip()
    # Use the first line (title) plus up to 200 chars of body as summary
    lines = content.split("\n")
    title = lines[0].strip()
    body_preview = " ".join(lines[1:]).strip()[:200]
    if body_preview:
        return f"{title} — {body_preview}"
    return title


INTERVIEW_BATCH_SIZE = DEFAULT_BATCH_SIZE


def _classify_interview_batch(
    batch: list[dict[str, Any]], post_summary: str
) -> list[dict[str, Any]]:
    response_block = "\n".join(
        f"[{i + 1}] [{iv.get('username', 'agent')}] {iv['response']}"
        for i, iv in enumerate(batch)
    )

    prompt = f"""Rate each person's understanding of the product AND their intent to engage.

The product: {post_summary}

Return ONLY valid JSON:
{{
  "ratings": [
    {{
      "index": 1,
      "clarity": "accurate" | "partial" | "wrong",
      "would_click": "yes" | "likely" | "unlikely" | "no",
      "would_signup": "yes" | "likely" | "unlikely" | "no"
    }}
  ]
}}

- clarity: "accurate" = correctly identifies product + audience, "partial" = gets some right, "wrong" = misunderstands
- would_click: based on their response, would they visit the link? Look for expressed curiosity or interest.
- would_signup: stricter — would they actually create an account? Look for explicit intent or strong enthusiasm.

Responses:
{response_block}"""

    raw = _ask_llm(prompt)
    parsed = _parse_llm_json(raw)
    return parsed.get("ratings", [])


def classify_interview_clarity(
    interviews: list[dict[str, Any]], post_summary: str, batch_size: int = 0
) -> dict[str, Any]:
    empty = {
        "score": 0.0,
        "accurate": 0,
        "partial": 0,
        "wrong": 0,
        "responses": [],
        "click_intent": {},
        "signup_intent": {},
    }
    if not interviews:
        return empty

    successful = [i for i in interviews if i.get("success") and i.get("response")]
    if not successful:
        return empty

    effective_batch = len(successful) if batch_size <= 0 else batch_size
    rating_map: dict[int, dict[str, str]] = {}
    offset = 0
    for start in range(0, len(successful), effective_batch):
        batch = successful[start : start + effective_batch]
        ratings = _classify_interview_batch(batch, post_summary)
        for r in ratings:
            idx = r.get("index", 0)
            if 1 <= idx <= len(batch):
                rating_map[offset + idx] = {
                    "clarity": r.get("clarity", "partial"),
                    "would_click": r.get("would_click", "unlikely"),
                    "would_signup": r.get("would_signup", "unlikely"),
                }
        offset += len(batch)

    accurate = 0
    partial = 0
    wrong = 0
    click_count = 0
    signup_count = 0
    click_positive = {"yes", "likely"}
    signup_positive = {"yes", "likely"}
    arch_click: dict[str, list[bool]] = {}
    arch_signup: dict[str, list[bool]] = {}
    responses: list[dict[str, Any]] = []

    for i, iv in enumerate(successful):
        r = rating_map.get(
            i + 1,
            {
                "clarity": "partial",
                "would_click": "unlikely",
                "would_signup": "unlikely",
            },
        )
        clarity = r["clarity"]
        would_click = r["would_click"]
        would_signup = r["would_signup"]

        if clarity == "accurate":
            accurate += 1
        elif clarity == "wrong":
            wrong += 1
        else:
            partial += 1

        clicked = would_click in click_positive
        signed_up = would_signup in signup_positive
        if clicked:
            click_count += 1
        if signed_up:
            signup_count += 1

        arch_label = str(iv.get("archetype") or "Unknown")
        arch_click.setdefault(arch_label, []).append(clicked)
        arch_signup.setdefault(arch_label, []).append(signed_up)

        responses.append(
            {
                "username": iv.get("username", "agent"),
                "archetype": arch_label,
                "response": iv.get("response", ""),
                "clarity": clarity,
                "would_click": would_click,
                "would_signup": would_signup,
            }
        )

    total = accurate + partial + wrong

    return {
        "score": _pct(accurate, total) if total else 0.0,
        "accurate": accurate,
        "partial": partial,
        "wrong": wrong,
        "total_interviewed": total,
        "responses": responses,
        "click_intent": {
            "count": click_count,
            "total": total,
            "rate": _pct(click_count, total),
            "by_archetype": {
                arch: _pct(sum(v), len(v)) for arch, v in arch_click.items()
            },
        },
        "signup_intent": {
            "count": signup_count,
            "total": total,
            "rate": _pct(signup_count, total),
            "by_archetype": {
                arch: _pct(sum(v), len(v)) for arch, v in arch_signup.items()
            },
        },
    }


def generate_scorecard(
    app_db_path: str, run_id: int, post_summary: str = "", batch_size: int = 0
) -> dict[str, Any]:
    metrics = query_engagement_metrics(app_db_path, run_id)
    participation = query_archetype_participation(app_db_path, run_id)
    comments, comment_archetypes = fetch_comments_with_archetypes(app_db_path, run_id)
    classifications = classify_comments(comments, batch_size=batch_size)
    timeline = query_engagement_timeline(app_db_path, run_id)
    depth = query_engagement_depth(app_db_path, run_id)

    interviews = load_interviews(app_db_path, run_id)

    scorecard = build_scorecard(
        metrics,
        participation,
        classifications,
        comment_archetypes,
        comments,
        engagement_timeline=timeline,
        engagement_depth=depth,
    )

    if interviews:
        if not post_summary:
            post_summary = _extract_post_summary(app_db_path, run_id)
        clarity_result = classify_interview_clarity(
            interviews, post_summary, batch_size=batch_size
        )
        scorecard["message_clarity"] = clarity_result

        if clarity_result.get("click_intent"):
            scorecard["click_through"] = clarity_result["click_intent"]
        if clarity_result.get("signup_intent"):
            scorecard["signup_funnel"] = {
                "would_click_count": clarity_result["click_intent"].get("count", 0),
                "would_signup_count": clarity_result["signup_intent"].get("count", 0),
                "total": clarity_result["signup_intent"].get("total", 0),
                "would_click_pct": clarity_result["click_intent"].get("rate", 0.0),
                "would_signup_pct": clarity_result["signup_intent"].get("rate", 0.0),
                "by_archetype": clarity_result["signup_intent"].get("by_archetype", {}),
            }

    scorecard["archetype_bios"] = _load_archetype_bios(app_db_path, run_id)
    save_scorecard(
        app_db_path,
        run_id,
        scorecard.get("score", 0.0),
        scorecard.get("grade", "F"),
        scorecard.get("summary", ""),
        json.dumps(scorecard),
    )
    return scorecard
