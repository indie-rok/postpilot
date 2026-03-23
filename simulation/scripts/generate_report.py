"""Report generator for OASIS Reddit simulation results.

Reads a SQLite DB produced by run_simulation.py and generates a formatted report
with engagement metrics, sentiment analysis, and actionable insights.

Two modes:
  --skip-llm: SQL queries only (no API keys needed)
  Full mode:  SQL queries + LLM calls for sentiment, themes, insights
"""

import argparse
import json
import os
import sqlite3
import sys
from typing import Any

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


# ---------------------------------------------------------------------------
# SQL query functions
# ---------------------------------------------------------------------------


def get_engagement_summary(db_path: str) -> dict[str, Any]:
    """Return engagement metrics from the simulation DB.

    Returns dict with: score, num_likes, num_dislikes, comment_count,
    total_agents, active_agents, engagement_rate.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Post-level metrics (aggregate across all posts)
    cur.execute(
        "SELECT COALESCE(SUM(num_likes), 0) AS num_likes, "
        "COALESCE(SUM(num_dislikes), 0) AS num_dislikes "
        "FROM post"
    )
    row = cur.fetchone()
    num_likes = row["num_likes"]
    num_dislikes = row["num_dislikes"]

    cur.execute("SELECT COUNT(*) AS cnt FROM comment")
    comment_count = cur.fetchone()["cnt"]

    cur.execute("SELECT COUNT(*) AS cnt FROM user")
    total_agents = cur.fetchone()["cnt"]

    # Active agents = distinct users who appear in the trace table
    cur.execute("SELECT COUNT(DISTINCT user_id) AS cnt FROM trace")
    active_agents = cur.fetchone()["cnt"]

    conn.close()

    engagement_rate = (active_agents / total_agents * 100) if total_agents else 0.0

    return {
        "score": num_likes - num_dislikes,
        "num_likes": num_likes,
        "num_dislikes": num_dislikes,
        "comment_count": comment_count,
        "total_agents": total_agents,
        "active_agents": active_agents,
        "engagement_rate": engagement_rate,
    }


def get_comments(db_path: str) -> list[dict[str, Any]]:
    """Return all comments joined with usernames."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT c.comment_id, c.post_id, c.user_id, c.content, c.num_likes, "
        "c.created_at, u.user_name "
        "FROM comment c JOIN user u ON c.user_id = u.user_id "
        "ORDER BY c.created_at"
    )
    comments = [dict(r) for r in cur.fetchall()]
    conn.close()
    return comments


def get_agent_actions(db_path: str) -> list[dict[str, Any]]:
    """Return all trace actions joined with usernames."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT t.user_id, t.action, t.info, t.created_at, "
        "u.user_name AS username "
        "FROM trace t JOIN user u ON t.user_id = u.user_id "
        "ORDER BY t.created_at"
    )
    actions = [dict(r) for r in cur.fetchall()]
    conn.close()
    return actions


def get_round_by_round(db_path: str, num_rounds: int = 10) -> list[dict[str, Any]]:
    """Approximate round-by-round engagement from trace timestamps.

    Divides the simulation timespan into `num_rounds` equal buckets and counts
    actions per bucket.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT MIN(created_at) AS t_min, MAX(created_at) AS t_max FROM trace")
    row = cur.fetchone()
    t_min, t_max = row["t_min"], row["t_max"]

    if not t_min or not t_max:
        conn.close()
        return []

    cur.execute("SELECT created_at, action FROM trace ORDER BY created_at")
    all_traces = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not all_traces:
        return []

    # Convert to simple ordinal position and bucket
    n = len(all_traces)
    rounds: list[dict[str, Any]] = []
    per_round = max(1, n // num_rounds)

    for i in range(num_rounds):
        start = i * per_round
        end = (i + 1) * per_round if i < num_rounds - 1 else n
        bucket = all_traces[start:end]
        actions_in_round = len(bucket)
        comments_in_round = sum(1 for a in bucket if a["action"] == "create_comment")
        likes_in_round = sum(1 for a in bucket if a["action"] == "like_post")
        rounds.append(
            {
                "round": i + 1,
                "actions": actions_in_round,
                "comments": comments_in_round,
                "likes": likes_in_round,
            }
        )

    return rounds


# ---------------------------------------------------------------------------
# LLM helper functions (require LLM_API_KEY)
# ---------------------------------------------------------------------------


def _create_llm_model():
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
    """Send a single prompt to the LLM and return the text response."""
    from camel.agents import ChatAgent
    from camel.messages import BaseMessage

    model = _create_llm_model()
    agent = ChatAgent(
        system_message="You are an expert analyst reviewing Reddit simulation data.",
        model=model,
    )
    user_msg = BaseMessage.make_user_message(role_name="User", content=prompt)
    response = agent.step(user_msg)
    return response.msgs[0].content


def classify_sentiment_llm(comments: list[dict[str, Any]]) -> dict[str, Any]:
    """Use LLM to classify each comment as supportive/neutral/skeptical.

    Returns dict with 'breakdown' (list of per-comment dicts) and
    'percentages' dict with supportive/neutral/skeptical percentages.
    """
    comment_texts = "\n".join(
        f"- [{c.get('user_name', 'unknown')}]: {c['content']}" for c in comments
    )
    prompt = (
        "Classify each comment below as exactly one of: supportive, neutral, skeptical.\n"
        "Return ONLY valid JSON: a list of objects with keys 'user_name', 'sentiment'.\n\n"
        f"Comments:\n{comment_texts}"
    )
    raw = _ask_llm(prompt)

    # Parse JSON from response (handle markdown fences)
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]

    try:
        breakdown = json.loads(text)
    except json.JSONDecodeError:
        breakdown = [
            {"user_name": c.get("user_name", "?"), "sentiment": "unknown"}
            for c in comments
        ]

    total = len(breakdown) or 1
    counts = {"supportive": 0, "neutral": 0, "skeptical": 0}
    for item in breakdown:
        s = item.get("sentiment", "unknown").lower()
        if s in counts:
            counts[s] += 1

    percentages = {k: round(v / total * 100, 1) for k, v in counts.items()}
    return {"breakdown": breakdown, "percentages": percentages}


def extract_themes_llm(comments: list[dict[str, Any]]) -> list[str]:
    """Use LLM to extract top recurring themes from comments."""
    comment_texts = "\n".join(f"- {c['content']}" for c in comments)
    prompt = (
        "Extract the top 3-5 recurring themes from these Reddit comments.\n"
        "Return ONLY a JSON list of short theme strings.\n\n"
        f"Comments:\n{comment_texts}"
    )
    raw = _ask_llm(prompt)

    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]

    try:
        themes = json.loads(text)
        if isinstance(themes, list):
            return [str(t) for t in themes]
    except json.JSONDecodeError:
        pass
    return ["(Could not parse themes from LLM response)"]


def generate_insights_llm(
    comments: list[dict[str, Any]],
    summary: dict[str, Any],
    themes: list[str],
) -> list[str]:
    """Use LLM to generate actionable recommendations from simulation data."""
    comment_texts = "\n".join(f"- {c['content']}" for c in comments[:10])
    prompt = (
        "Based on this Reddit simulation data, provide 3-5 actionable recommendations "
        "for the product team.\n\n"
        f"Engagement score: {summary.get('score')}\n"
        f"Likes: {summary.get('num_likes')}, Dislikes: {summary.get('num_dislikes')}\n"
        f"Comments: {summary.get('comment_count')}\n"
        f"Top themes: {', '.join(themes)}\n\n"
        f"Sample comments:\n{comment_texts}\n\n"
        "Return ONLY a JSON list of recommendation strings."
    )
    raw = _ask_llm(prompt)

    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]

    try:
        insights = json.loads(text)
        if isinstance(insights, list):
            return [str(i) for i in insights]
    except json.JSONDecodeError:
        pass
    return ["(Could not parse insights from LLM response)"]


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_report(db_path: str, skip_llm: bool = False) -> str:
    """Produce the full formatted report string.

    When skip_llm=True, sentiment/themes/insights sections show placeholders.
    """
    summary = get_engagement_summary(db_path)
    comments = get_comments(db_path)
    actions = get_agent_actions(db_path)
    rounds = get_round_by_round(db_path)

    lines: list[str] = []

    # ── Section 1: Engagement Summary ──
    lines.append("=" * 60)
    lines.append("ENGAGEMENT SUMMARY")
    lines.append("=" * 60)
    lines.append(f"  Score:            {summary['score']}")
    lines.append(f"  Likes:            {summary['num_likes']}")
    lines.append(f"  Dislikes:         {summary['num_dislikes']}")
    lines.append(f"  Comments:         {summary['comment_count']}")
    lines.append(f"  Total agents:     {summary['total_agents']}")
    lines.append(f"  Active agents:    {summary['active_agents']}")
    lines.append(f"  Engagement rate:  {summary['engagement_rate']:.1f}%")
    lines.append("")

    # ── Section 2: Sentiment Breakdown ──
    lines.append("=" * 60)
    lines.append("SENTIMENT BREAKDOWN")
    lines.append("=" * 60)
    if skip_llm:
        lines.append("  (LLM analysis skipped)")
        for c in comments:
            lines.append(f"  [{c.get('user_name', '?')}] sentiment: unknown")
    else:
        sentiment = classify_sentiment_llm(comments)
        pct = sentiment["percentages"]
        lines.append(f"  Supportive: {pct.get('supportive', 0)}%")
        lines.append(f"  Neutral:    {pct.get('neutral', 0)}%")
        lines.append(f"  Skeptical:  {pct.get('skeptical', 0)}%")
        lines.append("")
        for item in sentiment["breakdown"]:
            lines.append(
                f"  [{item.get('user_name', '?')}] sentiment: "
                f"{item.get('sentiment', 'unknown')}"
            )
    lines.append("")

    # ── Section 3: Top Themes ──
    lines.append("=" * 60)
    lines.append("TOP THEMES IN COMMENTS")
    lines.append("=" * 60)
    if skip_llm:
        lines.append("  (LLM analysis skipped)")
    else:
        themes = extract_themes_llm(comments)
        for i, theme in enumerate(themes, 1):
            lines.append(f"  {i}. {theme}")
    lines.append("")

    # ── Section 4: Agent-by-Agent Reactions ──
    lines.append("=" * 60)
    lines.append("AGENT-BY-AGENT REACTIONS")
    lines.append("=" * 60)

    # Group actions by username
    agent_map: dict[str, list[dict]] = {}
    for a in actions:
        uname = a.get("username", "unknown")
        agent_map.setdefault(uname, []).append(a)

    # Also attach comments per user
    comment_map: dict[str, list[dict]] = {}
    for c in comments:
        uname = c.get("user_name", "unknown")
        comment_map.setdefault(uname, []).append(c)

    all_usernames = sorted(set(list(agent_map.keys()) + list(comment_map.keys())))
    for uname in all_usernames:
        lines.append(f"\n  @{uname}")
        user_actions = agent_map.get(uname, [])
        user_comments = comment_map.get(uname, [])
        if user_actions:
            lines.append(f"    Actions: {', '.join(a['action'] for a in user_actions)}")
        if user_comments:
            for c in user_comments:
                snippet = c["content"][:80]
                lines.append(f'    Comment: "{snippet}"')
        if not user_actions and not user_comments:
            lines.append("    (no activity recorded)")
    lines.append("")

    # ── Section 5: Round-by-Round Engagement ──
    lines.append("=" * 60)
    lines.append("ROUND-BY-ROUND ENGAGEMENT")
    lines.append("=" * 60)
    if rounds:
        max_actions = max(r["actions"] for r in rounds) or 1
        for r in rounds:
            bar_len = int(r["actions"] / max_actions * 30)
            bar = "#" * bar_len
            lines.append(
                f"  Round {r['round']:>2}: {bar:<30} "
                f"({r['actions']} actions, {r['comments']} comments, {r['likes']} likes)"
            )
    else:
        lines.append("  (no trace data)")
    lines.append("")

    # ── Section 6: Actionable Insights ──
    lines.append("=" * 60)
    lines.append("ACTIONABLE INSIGHTS")
    lines.append("=" * 60)
    if skip_llm:
        lines.append("  (LLM analysis skipped)")
    else:
        themes_for_insights = locals().get("themes") or extract_themes_llm(comments)
        insights = generate_insights_llm(comments, summary, themes_for_insights)
        for i, insight in enumerate(insights, 1):
            lines.append(f"  {i}. {insight}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Generate a report from an OASIS simulation DB."
    )
    parser.add_argument("db_path", help="Path to the simulation SQLite database")
    parser.add_argument("--output", "-o", help="Write report to file instead of stdout")
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM calls (sentiment, themes, insights show placeholders)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.db_path):
        print(f"Error: DB not found: {args.db_path}", file=sys.stderr)
        sys.exit(1)

    report = format_report(args.db_path, skip_llm=args.skip_llm)

    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report written to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
