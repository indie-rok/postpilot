"""Core simulation runner — loads agents, seeds post, runs OASIS Reddit sim.

MiroFish-style time-based scheduling: 1 round = 1 simulated hour.
Each round, a random subset of agents is activated based on time-of-day
multipliers and per-archetype activity levels.
"""

import asyncio
import argparse
import json
import os
import random
import sys
from typing import Any

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from camel.models import ModelFactory
from camel.types import ModelPlatformType
import oasis
from oasis import ActionType, LLMAction, ManualAction

from config.simulation_config import PLATFORM_CONFIG, ACTIVITY_CONFIGS, TIME_CONFIG


def emit_progress(**kwargs: int | str) -> None:
    print(f"PROGRESS:{json.dumps(kwargs)}", flush=True)


def load_profiles(profiles_path: str) -> list[dict]:
    with open(profiles_path) as f:
        return json.load(f)


def get_archetype(username: str) -> str:
    archetype_map = {
        "founder_early": "saas_founder_early",
        "founder_scaled": "saas_founder_scaled",
        "skeptic": "skeptical_pm",
        "indie": "indie_hacker",
        "hr": "hr_people_ops",
        "lurker": "lurker",
        "regular": "community_regular",
        "vc": "vc_growth",
    }
    for prefix, archetype in archetype_map.items():
        if prefix in username:
            return archetype
    return "saas_founder_early"


def create_model():
    """Reads from env vars: LLM_API_KEY, LLM_BASE_URL, LLM_MODEL"""
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise ValueError("LLM_API_KEY not set in environment")

    base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    model_type = os.getenv("LLM_MODEL", "arcee-ai/trinity-mini:free")

    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=model_type,
        api_key=api_key,
        url=base_url,
        model_config_dict={"temperature": 0.8},
    )


def load_post_content(post_path: str) -> str:
    with open(post_path) as f:
        return f.read().strip()


def get_time_multiplier(hour: int) -> float:
    if hour in TIME_CONFIG["peak_hours"]:
        return TIME_CONFIG["peak_multiplier"]
    if hour in TIME_CONFIG["off_peak_hours"]:
        return TIME_CONFIG["off_peak_multiplier"]
    return TIME_CONFIG["normal_multiplier"]


def get_active_agents_for_hour(agents: list, hour: int) -> list:
    """MiroFish-style: randomly select a subset of agents based on time-of-day."""
    multiplier = get_time_multiplier(hour % 24)
    target_count = int(
        random.uniform(
            TIME_CONFIG["agents_per_hour_min"],
            TIME_CONFIG["agents_per_hour_max"],
        )
        * multiplier
    )

    candidates = []
    for agent_id, agent in agents:
        username = agent.user_info.user_name or agent.user_info.name or ""
        archetype = get_archetype(username)
        config = ACTIVITY_CONFIGS.get(archetype)
        if not config:
            candidates.append((agent_id, agent))
            continue

        if (hour % 24) not in config["active_hours"]:
            continue

        if random.random() < config["activity_level"]:
            candidates.append((agent_id, agent))

    if not candidates:
        return []

    selected = random.sample(candidates, min(target_count, len(candidates)))
    return selected


async def run_simulation(post_path, profiles_path, tag, results_dir):
    print(f"=== Starting simulation: {tag} ===")

    profiles = load_profiles(profiles_path)
    post_content = load_post_content(post_path)
    model = create_model()
    total_hours = TIME_CONFIG["total_hours"]
    minutes_per_round = TIME_CONFIG["minutes_per_round"]
    total_rounds = (total_hours * 60) // minutes_per_round

    print(f"Loaded {len(profiles)} agent profiles")
    print(f"Post length: {len(post_content)} chars")
    print(
        f"Simulating {total_hours}h ({total_rounds} rounds, {minutes_per_round}min/round)"
    )

    available_actions = ActionType.get_default_reddit_actions()

    agent_graph = await oasis.generate_reddit_agent_graph(
        profile_path=profiles_path,
        model=model,
        available_actions=available_actions,
    )

    db_path = os.path.join(results_dir, f"{tag}.db")
    env = oasis.make(
        agent_graph=agent_graph,
        platform=oasis.DefaultPlatformType.REDDIT,
        database_path=db_path,
        semaphore=10,
    )

    await env.reset()
    print(f"Environment initialized. DB: {db_path}")

    agents = list(env.agent_graph.get_agents())
    op_agent_id, op_agent = agents[0]

    seed_action: dict[Any, Any] = {
        op_agent: ManualAction(
            action_type=ActionType.CREATE_POST,
            action_args={"content": post_content},
        )
    }
    await env.step(seed_action)
    print(f"Post seeded by {op_agent.user_info.user_name or op_agent.user_info.name}")

    start_hour = TIME_CONFIG.get("start_hour", 9)

    engaged_agent_ids: set[int] = set()

    for round_num in range(total_rounds):
        simulated_minutes = round_num * minutes_per_round
        simulated_hour = ((simulated_minutes // 60) + start_hour) % 24
        print(
            f"\n--- Round {round_num + 1}/{total_rounds} (simulated {simulated_hour:02d}:{simulated_minutes % 60:02d}) ---"
        )

        active = get_active_agents_for_hour(agents, simulated_hour)
        print(f"Active agents: {len(active)}/{len(agents)}")

        if not active:
            continue

        for aid, _ in active:
            engaged_agent_ids.add(aid)

        round_actions: dict[Any, Any] = {agent: LLMAction() for _, agent in active}
        await env.step(round_actions)

    print(f"\n=== Simulation complete: {tag} ===")
    print(f"Results saved to: {db_path}")

    interviews = await run_interviews(agents, engaged_agent_ids)
    interviews_path = os.path.join(results_dir, f"{tag}_interviews.json")
    with open(interviews_path, "w") as f:
        json.dump(interviews, f, indent=2, ensure_ascii=False)
    print(f"Interviews saved: {len(interviews)} responses → {interviews_path}")

    await env.close()
    return db_path


INTERVIEW_PROMPT = (
    "Based on the Reddit post you just read and the discussion that followed, "
    "answer these three questions:\n"
    "1. What does this product do and who is it for?\n"
    "2. Would you click the link to check it out? Why or why not?\n"
    "3. Would you actually sign up or try it? Why or why not?"
)


async def run_interviews(agents: list, engaged_ids: set[int]) -> list[dict]:
    print("\n--- Running post-simulation interviews ---")
    skipped = [aid for aid, _ in agents if aid not in engaged_ids]
    if skipped:
        print(f"  Skipping {len(skipped)} agents that were never activated")
    results = []
    for agent_id, agent in agents:
        if agent_id not in engaged_ids:
            continue
        username = agent.user_info.user_name or agent.user_info.name or ""
        try:
            response = await agent.perform_interview(INTERVIEW_PROMPT)
            results.append(
                {
                    "user_id": agent_id,
                    "username": username,
                    "archetype": get_archetype(username),
                    "response": response.get("content", ""),
                    "success": response.get("success", False),
                }
            )
            print(f"  Interviewed {username}: {response.get('content', '')[:80]}...")
        except Exception as exc:
            print(f"  Interview failed for {username}: {exc}")
            results.append(
                {
                    "user_id": agent_id,
                    "username": username,
                    "archetype": get_archetype(username),
                    "response": "",
                    "success": False,
                }
            )
    return results


def main():
    parser = argparse.ArgumentParser(description="Run Reddit post simulation")
    parser.add_argument("--post", required=True, help="Path to post text file")
    parser.add_argument(
        "--tag", required=True, help="Run tag (determines output DB name)"
    )
    parser.add_argument(
        "--profiles",
        default=os.path.join(
            os.path.dirname(__file__), "..", "profiles", "r_saas_community.json"
        ),
        help="Path to agent profiles JSON",
    )
    parser.add_argument(
        "--results-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "results"),
        help="Directory for result DBs",
    )
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)

    asyncio.run(
        run_simulation(
            post_path=args.post,
            profiles_path=args.profiles,
            tag=args.tag,
            results_dir=args.results_dir,
        )
    )


if __name__ == "__main__":
    main()
