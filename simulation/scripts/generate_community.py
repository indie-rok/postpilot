# pyright: reportMissingImports=false, reportImplicitRelativeImport=false

from __future__ import annotations

import json
import os
import sys
from typing import Any

import praw
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db import (
    create_community,
    get_community_by_subreddit,
    save_community_profiles,
)


def scrape_subreddit(
    subreddit_name: str,
    client_id: str,
    client_secret: str,
    post_limit: int = 25,
    comment_limit: int = 50,
) -> dict[str, Any]:
    name = subreddit_name.replace("r/", "").strip("/")

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent="reddit-sim/1.0 (community-scraper)",
    )

    sub = reddit.subreddit(name)

    rules: list[dict[str, str]] = []
    try:
        for rule in sub.rules:
            rules.append(
                {"name": rule.short_name, "description": (rule.description or "")[:500]}
            )
    except Exception:
        pass

    info: dict[str, Any] = {
        "name": f"r/{name}",
        "title": sub.title,
        "description": (sub.public_description or "")[:2000],
        "subscribers": sub.subscribers,
        "rules": rules,
    }

    posts: list[dict[str, Any]] = []
    seen_authors: dict[str, int] = {}
    all_comments: list[dict[str, Any]] = []
    link_flairs: list[str] = []

    for post in sub.hot(limit=post_limit):
        posts.append(
            {
                "title": post.title,
                "score": post.score,
                "num_comments": post.num_comments,
                "upvote_ratio": post.upvote_ratio,
                "selftext": (post.selftext or "")[:500],
                "link_flair": post.link_flair_text,
            }
        )

        if post.link_flair_text and post.link_flair_text not in link_flairs:
            link_flairs.append(post.link_flair_text)

        post.comments.replace_more(limit=0)
        for comment in post.comments[:5]:
            if not hasattr(comment, "body") or not comment.body:
                continue
            author_name = str(comment.author) if comment.author else "[deleted]"
            if author_name != "[deleted]":
                seen_authors[author_name] = seen_authors.get(author_name, 0) + 1

            if len(all_comments) < comment_limit:
                all_comments.append(
                    {
                        "body": comment.body[:500],
                        "score": comment.score,
                        "author": author_name,
                    }
                )

    top_authors = sorted(seen_authors.items(), key=lambda x: x[1], reverse=True)[:20]

    return {
        "info": info,
        "posts": posts,
        "comments": all_comments,
        "link_flairs": link_flairs,
        "top_authors": [{"name": a, "comment_count": c} for a, c in top_authors],
    }


def _create_model():
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType

    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=os.getenv("LLM_MODEL", "gpt-5-mini"),
        api_key=os.getenv("LLM_API_KEY"),
        url=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        model_config_dict={"temperature": 0.7},
    )


def _ask_llm(system_message: str, prompt: str) -> str:
    from camel.agents import ChatAgent
    from camel.messages import BaseMessage

    agent = ChatAgent(model=_create_model(), system_message=system_message)
    msg = BaseMessage.make_user_message(role_name="User", content=prompt)
    response = agent.step(msg)
    return response.msgs[0].content


def _parse_llm_json(raw: str) -> list[dict[str, Any]]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "personas" in result:
            personas = result["personas"]
            return personas if isinstance(personas, list) else []
        return []
    except (json.JSONDecodeError, ValueError):
        return []


PERSONA_GENERATION_PROMPT = """Based on the following subreddit community data, generate {count} diverse user personas that represent the typical members of this community.

SUBREDDIT: {subreddit}
DESCRIPTION: {description}
SUBSCRIBERS: {subscribers}
LINK FLAIRS: {flairs}

TOP POSTS (titles + engagement):
{posts_summary}

SAMPLE COMMENTS (showing community voice/tone):
{comments_summary}

MOST ACTIVE USERS:
{authors_summary}

---

Generate exactly {count} personas. Each persona should represent a DIFFERENT archetype of community member — vary their engagement style, expertise level, sentiment tendency, and background.

For each persona, return a JSON object with these fields:
- "username": a realistic Reddit-style username (lowercase, underscores ok)
- "realname": a realistic full name
- "archetype": a short label for this persona type (e.g. "Power User", "Skeptic", "Lurker", "Industry Expert", "Newbie", "Enthusiast")
- "bio": one sentence about who they are
- "persona": a detailed behavioral description (150-250 words) explaining how this person engages in {subreddit} — their posting style, what they upvote/downvote, typical reactions, knowledge level, biases, and tone. This is the most important field — it drives the simulation.
- "age": realistic age (18-65)
- "gender": "male" or "female"
- "mbti": a realistic MBTI type
- "country": country of residence
- "profession": their job title/profession
- "interested_topics": list of 3-5 topics they follow

Return ONLY a JSON array of {count} objects. No explanation, no markdown formatting outside the JSON."""


def generate_personas(
    scraped_data: dict[str, Any],
    persona_count: int = 18,
) -> list[dict[str, Any]]:
    info = scraped_data["info"]
    posts = scraped_data.get("posts", [])
    comments = scraped_data.get("comments", [])
    top_authors = scraped_data.get("top_authors", [])
    flairs = scraped_data.get("link_flairs", [])

    posts_summary = "\n".join(
        f"- [{p['score']} pts, {p['num_comments']} comments] {p['title']}"
        for p in posts[:15]
    )

    comments_summary = "\n".join(
        f"- ({c['score']} pts, u/{c['author']}): {c['body'][:200]}"
        for c in comments[:20]
    )

    authors_summary = "\n".join(
        f"- u/{a['name']} ({a['comment_count']} comments)" for a in top_authors[:10]
    )

    prompt = PERSONA_GENERATION_PROMPT.format(
        count=persona_count,
        subreddit=info["name"],
        description=info.get("description", "No description"),
        subscribers=info.get("subscribers", "unknown"),
        flairs=", ".join(flairs) if flairs else "none",
        posts_summary=posts_summary or "No posts available",
        comments_summary=comments_summary or "No comments available",
        authors_summary=authors_summary or "No author data",
    )

    raw = _ask_llm(
        "You generate realistic Reddit user personas based on community data. Return ONLY valid JSON.",
        prompt,
    )

    personas = _parse_llm_json(raw)

    required_fields = {"username", "realname", "archetype", "persona"}
    validated: list[dict[str, Any]] = []
    for p in personas:
        if not isinstance(p, dict):
            continue
        if not required_fields.issubset(p.keys()):
            continue
        validated.append(p)

    return validated


def generate_community(
    subreddit: str,
    persona_count: int,
    db_path: str,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    cid = client_id or os.getenv("REDDIT_CLIENT_ID", "")
    csecret = client_secret or os.getenv("REDDIT_CLIENT_SECRET", "")

    if not cid or not csecret:
        raise RuntimeError("Reddit API keys not configured")

    scraped = scrape_subreddit(subreddit, cid, csecret)

    existing = get_community_by_subreddit(db_path, scraped["info"]["name"])
    if existing:
        community_id = int(existing["id"])
    else:
        community_id = create_community(
            db_path,
            scraped["info"]["name"],
            raw_data=json.dumps(scraped, default=str),
            status="generating",
        )

    personas = generate_personas(scraped, persona_count)

    if not personas:
        raise RuntimeError("LLM failed to generate valid personas")

    save_community_profiles(db_path, community_id, personas, replace=True)

    return community_id, personas
