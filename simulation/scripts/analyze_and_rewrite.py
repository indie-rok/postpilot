"""Analyze simulation comments and generate an improved post."""

import argparse
import json
import os
import sqlite3
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


def _create_model():
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType

    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=os.getenv("LLM_MODEL", "gpt-5-mini"),
        api_key=os.getenv("LLM_API_KEY"),
        url=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        model_config_dict={"temperature": 0.3},
    )


def _ask_llm(prompt: str, system: str = "") -> str:
    from camel.agents import ChatAgent
    from camel.messages import BaseMessage

    agent = ChatAgent(model=_create_model(), system_message=system)
    msg = BaseMessage.make_user_message(role_name="User", content=prompt)
    response = agent.step(msg)
    return response.msgs[0].content


def get_comments(db_path: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT COALESCE(u.user_name, u.name), c.content "
        "FROM comment c JOIN user u ON c.user_id = u.user_id "
        "WHERE c.post_id = 1 ORDER BY c.created_at"
    )
    comments = [{"author": r[0], "content": r[1]} for r in cur.fetchall()]
    conn.close()
    return comments


def get_original_post(db_path: str) -> str:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT content FROM post WHERE post_id = 1")
    content = cur.fetchone()[0]
    conn.close()
    return content


def analyze(comments: list[dict]) -> str:
    comments_text = "\n\n".join(f"[{c['author']}]: {c['content']}" for c in comments)

    from prompts.rewrite import ANALYZE as ANALYZE_PROMPT, ANALYZE_SYSTEM
    prompt = ANALYZE_PROMPT.format(comments_text=comments_text)

    print("Analyzing comments...")
    return _ask_llm(prompt, system=ANALYZE_SYSTEM)


def rewrite(original_post: str, analysis: str) -> str:
    from prompts.rewrite import REWRITE as REWRITE_PROMPT, REWRITE_SYSTEM
    prompt = REWRITE_PROMPT.format(original_post=original_post, analysis=analysis)

    print("Generating improved post...")
    return _ask_llm(prompt, system=REWRITE_SYSTEM)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze simulation feedback and generate improved post"
    )
    parser.add_argument("db", help="Path to simulation SQLite DB")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "results"),
    )
    args = parser.parse_args()

    comments = get_comments(args.db)
    original_post = get_original_post(args.db)
    print(f"Loaded {len(comments)} comments from simulation")

    analysis = analyze(comments)

    analysis_path = os.path.join(args.output_dir, "analysis.md")
    with open(analysis_path, "w") as f:
        f.write(analysis)
    print(f"Analysis saved to {analysis_path}")

    improved = rewrite(original_post, analysis)

    improved_path = os.path.join(args.output_dir, "improved-post.md")
    with open(improved_path, "w") as f:
        f.write(improved)
    print(f"Improved post saved to {improved_path}")

    print("\nDone. Next steps:")
    print(f"  1. Review the analysis: cat {analysis_path}")
    print(f"  2. Review the improved post: cat {improved_path}")
    print(
        f"  3. Re-simulate: python scripts/run_simulation.py --post {improved_path} --tag v2-improved"
    )
    print(
        f"  4. Compare: python scripts/compare_runs.py results/v1-original.db results/v2-improved.db --skip-llm"
    )


if __name__ == "__main__":
    main()
