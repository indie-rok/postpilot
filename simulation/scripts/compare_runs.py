"""Compare multiple OASIS simulation runs side-by-side.

Reads SQLite DBs produced by run_simulation.py and produces a formatted
comparison table with engagement metrics, sentiment analysis, and winner.

Two modes:
  --skip-llm: SQL queries only (no API keys needed)
  Full mode:  SQL queries + LLM calls for sentiment and themes

CLI: python compare_runs.py <db1> <db2> [db3...] [--output FILE] [--skip-llm]
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


def load_run_metrics(db_path: str) -> dict[str, Any]:
    """Load engagement metrics from a simulation DB.

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


def _get_comments(db_path: str) -> list[dict[str, Any]]:
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


# ---------------------------------------------------------------------------
# LLM helper functions (require LLM_API_KEY)
# ---------------------------------------------------------------------------


def _create_llm_model():
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType

    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=os.getenv("LLM_MODEL", "openai/gpt-5.4-nano"),
        api_key=os.getenv("LLM_API_KEY"),
        url=os.getenv("LLM_BASE_URL", "https://api.minimax.chat/v1"),
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


def _parse_json_from_llm(raw: str) -> Any:
    """Parse JSON from LLM response, handling markdown fences."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    return json.loads(text)


def get_sentiment_distribution(db_path: str) -> dict[str, float]:
    """Use LLM to classify comments and return sentiment percentages.

    Returns dict with supportive_pct, neutral_pct, skeptical_pct.
    """
    comments = _get_comments(db_path)
    if not comments:
        return {"supportive_pct": 0.0, "neutral_pct": 0.0, "skeptical_pct": 0.0}

    comment_texts = "\n".join(
        f"- [{c.get('user_name', 'unknown')}]: {c['content']}" for c in comments
    )
    prompt = (
        "Classify each comment below as exactly one of: supportive, neutral, skeptical.\n"
        "Return ONLY valid JSON: a list of objects with keys 'user_name', 'sentiment'.\n\n"
        f"Comments:\n{comment_texts}"
    )
    raw = _ask_llm(prompt)

    try:
        breakdown = _parse_json_from_llm(raw)
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

    return {
        "supportive_pct": round(counts["supportive"] / total * 100, 1),
        "neutral_pct": round(counts["neutral"] / total * 100, 1),
        "skeptical_pct": round(counts["skeptical"] / total * 100, 1),
    }


def get_key_themes(db_path: str) -> list[str]:
    """Use LLM to extract top recurring themes from comments."""
    comments = _get_comments(db_path)
    if not comments:
        return []

    comment_texts = "\n".join(f"- {c['content']}" for c in comments)
    prompt = (
        "Extract the top 3-5 recurring themes from these Reddit comments.\n"
        "Return ONLY a JSON list of short theme strings.\n\n"
        f"Comments:\n{comment_texts}"
    )
    raw = _ask_llm(prompt)

    try:
        themes = _parse_json_from_llm(raw)
        if isinstance(themes, list):
            return [str(t) for t in themes]
    except json.JSONDecodeError:
        pass
    return ["(Could not parse themes from LLM response)"]


# ---------------------------------------------------------------------------
# Comparison logic
# ---------------------------------------------------------------------------


def determine_winner(all_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Determine the winning run by highest score.

    Ties broken by supportive_pct (NOT engagement_rate).
    Falls back to first entry if still tied.
    """
    if not all_metrics:
        raise ValueError("No metrics provided")

    return max(
        all_metrics,
        key=lambda m: (m.get("score", 0), m.get("supportive_pct", 0.0)),
    )


def format_comparison(all_metrics: list[dict[str, Any]]) -> str:
    """Format a side-by-side comparison table of all runs.

    Includes: score, upvotes, downvotes, comments, engagement rate,
    sentiment percentages, key themes, and winner designation.
    """
    winner = determine_winner(all_metrics)
    winner_tag = winner.get("tag", "?")

    lines: list[str] = []

    # Header
    lines.append("=" * 70)
    lines.append("SIMULATION COMPARISON")
    lines.append("=" * 70)
    lines.append("")

    # Build column headers
    tags = [m.get("tag", f"run{i + 1}") for i, m in enumerate(all_metrics)]
    col_width = max(12, max(len(t) for t in tags) + 4)

    header = f"{'Metric':<22}" + "".join(f"{t:>{col_width}}" for t in tags)
    lines.append(header)
    lines.append("-" * len(header))

    # Row helper
    def _row(label: str, key: str, fmt: str = "{}") -> str:
        cells = []
        for m in all_metrics:
            val = m.get(key, "-")
            if val == "-" or val is None:
                cells.append(f"{'-':>{col_width}}")
            else:
                cells.append(f"{fmt.format(val):>{col_width}}")
        return f"{label:<22}" + "".join(cells)

    # Engagement metrics
    lines.append(_row("Final Score", "score"))
    lines.append(_row("Upvotes", "num_likes"))
    lines.append(_row("Downvotes", "num_dislikes"))
    lines.append(_row("Comments", "comment_count"))
    lines.append(_row("Engagement Rate", "engagement_rate", "{:.1f}%"))
    lines.append("")

    # Sentiment (may be absent if --skip-llm)
    lines.append(_row("Supportive %", "supportive_pct", "{:.1f}%"))
    lines.append(_row("Neutral %", "neutral_pct", "{:.1f}%"))
    lines.append(_row("Skeptical %", "skeptical_pct", "{:.1f}%"))
    lines.append("")

    # Key themes per variant
    lines.append("-" * len(header))
    lines.append("KEY THEMES")
    lines.append("-" * len(header))
    for m in all_metrics:
        tag = m.get("tag", "?")
        themes = m.get("themes", [])
        if themes:
            lines.append(f"  {tag}:")
            for i, theme in enumerate(themes, 1):
                lines.append(f"    {i}. {theme}")
        else:
            lines.append(f"  {tag}: (no themes)")
    lines.append("")

    # Winner
    lines.append("=" * len(header))
    lines.append(f"WINNER: {winner_tag} (score={winner.get('score', '?')})")
    lines.append("=" * len(header))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Compare multiple OASIS simulation runs side-by-side."
    )
    parser.add_argument(
        "db_paths",
        nargs="+",
        help="Paths to simulation SQLite databases to compare",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Write comparison to file instead of stdout",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM calls (sentiment/themes show placeholders)",
    )
    args = parser.parse_args()

    if len(args.db_paths) < 2:
        print("Error: need at least 2 DB paths to compare", file=sys.stderr)
        sys.exit(1)

    # Validate all paths exist
    for p in args.db_paths:
        if not os.path.exists(p):
            print(f"Error: DB not found: {p}", file=sys.stderr)
            sys.exit(1)

    # Load metrics for each run
    all_metrics: list[dict[str, Any]] = []
    for i, db_path in enumerate(args.db_paths):
        tag = os.path.splitext(os.path.basename(db_path))[0]
        if not tag:
            tag = f"run{i + 1}"

        metrics = load_run_metrics(db_path)
        metrics["tag"] = tag

        if not args.skip_llm:
            sentiment = get_sentiment_distribution(db_path)
            metrics.update(sentiment)
            metrics["themes"] = get_key_themes(db_path)
        else:
            metrics["supportive_pct"] = "-"
            metrics["neutral_pct"] = "-"
            metrics["skeptical_pct"] = "-"
            metrics["themes"] = []

        all_metrics.append(metrics)

    output = format_comparison(all_metrics)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Comparison written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
