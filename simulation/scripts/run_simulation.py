# pyright: reportMissingImports=false, reportImplicitRelativeImport=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportAny=false, reportExplicitAny=false, reportUnusedImport=false, reportUnusedVariable=false, reportUnusedCallResult=false

"""Core simulation runner — loads agents, seeds post, runs OASIS Reddit sim.

MiroFish-style time-based scheduling: 1 round = 1 simulated hour.
Each round, a random subset of agents is activated based on time-of-day
multipliers and per-archetype activity levels.
"""

import asyncio
import argparse
import json
import logging
import os
import random
import sys
from datetime import datetime, timezone
from typing import Any, cast

# Silence OASIS/camel internal loggers — they dump full LLM conversations to stderr
for _logger_name in ("social", "oasis", "camel"):
    logging.getLogger(_logger_name).setLevel(logging.WARNING)

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from camel.models import ModelFactory
from camel.types import ModelPlatformType
import oasis
from oasis import ActionType, LLMAction, ManualAction

from config.simulation_config import PLATFORM_CONFIG, ACTIVITY_CONFIGS, TIME_CONFIG
from db import (
    extract_oasis_results,
    get_agent_mapping,
    insert_interview,
    update_oasis_user_id,
    update_run_status,
)


def emit_progress(**kwargs: int | str) -> None:
    print(f"PROGRESS:{json.dumps(kwargs)}", flush=True)


SIM_TIME_CONFIG = cast(dict[str, Any], TIME_CONFIG)
SIM_ACTIVITY_CONFIGS = cast(dict[str, dict[str, Any]], ACTIVITY_CONFIGS)


def load_profiles(profiles_path: str) -> list[dict[str, Any]]:
    with open(profiles_path) as f:
        return cast(list[dict[str, Any]], json.load(f))


# Mapping from display archetype names (from DB) to config keys
ARCHETYPE_TO_CONFIG_KEY = {
    "Early Founder": "saas_founder_early",
    "Scaled Founder": "saas_founder_scaled",
    "Skeptical PM": "skeptical_pm",
    "Indie Hacker": "indie_hacker",
    "HR/People Ops": "hr_people_ops",
    "Lurker": "lurker",
    "Community Regular": "community_regular",
    "VC/Growth": "vc_growth",
}


def create_model():
    """Reads from env vars: LLM_API_KEY, LLM_BASE_URL, LLM_MODEL"""
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise ValueError("LLM_API_KEY not set in environment")

    base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    model_type = os.getenv("LLM_MODEL", "gpt-5-mini")

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
    peak_hours = cast(list[int], SIM_TIME_CONFIG["peak_hours"])
    off_peak_hours = cast(list[int], SIM_TIME_CONFIG["off_peak_hours"])

    if hour in peak_hours:
        return float(SIM_TIME_CONFIG["peak_multiplier"])
    if hour in off_peak_hours:
        return float(SIM_TIME_CONFIG["off_peak_multiplier"])
    return float(SIM_TIME_CONFIG["normal_multiplier"])


def get_active_agents_for_hour(
    agents: list[tuple[int, Any]],
    hour: int,
    username_to_archetype: dict[str, str] | None = None,
) -> list[tuple[int, Any]]:
    """MiroFish-style: randomly select a subset of agents based on time-of-day."""
    multiplier = get_time_multiplier(hour % 24)
    target_count = int(
        random.uniform(
            float(SIM_TIME_CONFIG["agents_per_hour_min"]),
            float(SIM_TIME_CONFIG["agents_per_hour_max"]),
        )
        * multiplier
    )

    candidates = []
    for agent_id, agent in agents:
        username = agent.user_info.user_name or agent.user_info.name or ""
        display_archetype = (
            username_to_archetype.get(username, "Community Regular")
            if username_to_archetype
            else "Community Regular"
        )
        config_key = ARCHETYPE_TO_CONFIG_KEY.get(display_archetype, "community_regular")
        config = SIM_ACTIVITY_CONFIGS.get(config_key)
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


async def run_simulation(
    post_path,
    profiles_path,
    tag,
    results_dir,
    run_id=None,
    app_db_path=None,
):
    print("Preparing simulation...")

    profiles = load_profiles(profiles_path)
    username_to_archetype = {
        p["username"]: p.get("archetype", "Community Regular") for p in profiles
    }
    post_content = load_post_content(post_path)
    model = create_model()
    total_hours = int(SIM_TIME_CONFIG["total_hours"])
    minutes_per_round = int(SIM_TIME_CONFIG["minutes_per_round"])
    total_rounds = (total_hours * 60) // minutes_per_round

    llm_calls = 0
    emit_progress(phase="setup", total_rounds=total_rounds, total_agents=len(profiles))

    print(f"{len(profiles)} agents loaded")

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
    print("Environment ready")

    agents = list(env.agent_graph.get_agents())
    oasis_to_run_agent: dict[int, int] = {}
    if app_db_path is not None and run_id is not None:
        oasis_username_to_agent_id: dict[str, int] = {}
        for oasis_agent_id, agent in agents:
            username = agent.user_info.user_name or agent.user_info.name or ""
            if username:
                oasis_username_to_agent_id[username] = int(oasis_agent_id)

        run_agent_mapping = get_agent_mapping(app_db_path, run_id)
        for username, oasis_agent_id in oasis_username_to_agent_id.items():
            run_agent_id = run_agent_mapping.get(username)
            if run_agent_id is None:
                continue
            update_oasis_user_id(app_db_path, run_agent_id, oasis_agent_id)
            oasis_to_run_agent[oasis_agent_id] = run_agent_id

    op_agent_id, op_agent = agents[0]

    seed_action: dict[Any, Any] = {
        op_agent: ManualAction(
            action_type=ActionType.CREATE_POST,
            action_args={"content": post_content},
        )
    }
    await env.step(seed_action)
    if app_db_path is not None and run_id is not None:
        update_run_status(app_db_path, run_id, "running")
    print(
        f"Post published by {op_agent.user_info.user_name or op_agent.user_info.name}"
    )

    start_hour = int(SIM_TIME_CONFIG.get("start_hour", 9))

    engaged_agent_ids: set[int] = set()

    for round_num in range(total_rounds):
        simulated_minutes = round_num * minutes_per_round
        simulated_hour = ((simulated_minutes // 60) + start_hour) % 24
        current_hour = (round_num * minutes_per_round) // 60 + 1
        print(f"Hour {current_hour}/{total_hours}")

        active = get_active_agents_for_hour(
            agents, simulated_hour, username_to_archetype
        )
        print(f"{len(active)} agents responding")

        simulated_time = f"{simulated_hour:02d}:{simulated_minutes % 60:02d}"
        emit_progress(
            phase="simulation",
            round=round_num + 1,
            total_rounds=total_rounds,
            total_hours=total_hours,
            hour=simulated_time,
            active_agents=len(active),
            llm_calls=llm_calls,
        )

        if not active:
            continue

        for aid, _ in active:
            engaged_agent_ids.add(aid)

        round_actions: dict[Any, Any] = {agent: LLMAction() for _, agent in active}
        await env.step(round_actions)

        llm_calls += len(active)

    print("Simulation complete")

    interviews, llm_calls = await run_interviews(
        agents,
        engaged_agent_ids,
        llm_calls,
        app_db_path=app_db_path,
        run_id=run_id,
        oasis_to_run_agent=oasis_to_run_agent,
        username_to_archetype=username_to_archetype,
    )

    interview_count = len(interviews) if isinstance(interviews, list) else 0
    print(f"{interview_count} interviews complete")

    emit_progress(phase="complete", llm_calls=llm_calls)

    await env.close()

    # Extract OASIS results AFTER env.close() to ensure all data is flushed to SQLite
    if app_db_path is not None and run_id is not None:
        extract_oasis_results(app_db_path, db_path, run_id, oasis_to_run_agent)
        update_run_status(
            app_db_path,
            run_id,
            "complete",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    return db_path


from prompts.simulation import INTERVIEW as INTERVIEW_PROMPT


async def run_interviews(
    agents: list[tuple[int, Any]],
    engaged_ids: set[int],
    llm_calls: int = 0,
    app_db_path: str | None = None,
    run_id: int | None = None,
    oasis_to_run_agent: dict[int, int] | None = None,
    username_to_archetype: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    print("Interviewing agents...")
    skipped = [aid for aid, _ in agents if aid not in engaged_ids]
    if skipped:
        print(f"Skipped {len(skipped)} inactive agents")

    interview_total = sum(1 for aid, _ in agents if aid in engaged_ids)
    if interview_total == 0:
        return ([], llm_calls)
    emit_progress(phase="interview", current=0, total=interview_total)

    results = []
    interview_idx = 0
    for agent_id, agent in agents:
        if agent_id not in engaged_ids:
            continue
        username = agent.user_info.user_name or agent.user_info.name or ""
        agent_id_for_db = None
        if oasis_to_run_agent is not None:
            agent_id_for_db = oasis_to_run_agent.get(agent_id)
        try:
            response = await agent.perform_interview(INTERVIEW_PROMPT)
            response_text = response.get("content", "")
            display_archetype = (
                username_to_archetype.get(username, "Community Regular")
                if username_to_archetype
                else "Unknown"
            )
            results.append(
                {
                    "user_id": agent_id,
                    "username": username,
                    "archetype": display_archetype,
                    "response": response_text,
                    "success": response.get("success", False),
                }
            )
            print(f"Interviewed {username} ✓")
            if app_db_path is not None and run_id is not None:
                insert_interview(app_db_path, run_id, agent_id_for_db, response_text)
            interview_idx += 1
            llm_calls += 1
            emit_progress(
                phase="interview",
                current=interview_idx,
                total=interview_total,
                agent=username,
                llm_calls=llm_calls,
            )
        except Exception as exc:
            print(f"Interview failed: {username}")
            response_text = ""
            display_archetype = (
                username_to_archetype.get(username, "Community Regular")
                if username_to_archetype
                else "Unknown"
            )
            results.append(
                {
                    "user_id": agent_id,
                    "username": username,
                    "archetype": display_archetype,
                    "response": response_text,
                    "success": False,
                }
            )
            if app_db_path is not None and run_id is not None:
                insert_interview(app_db_path, run_id, agent_id_for_db, response_text)
            interview_idx += 1
            llm_calls += 1
            emit_progress(
                phase="interview",
                current=interview_idx,
                total=interview_total,
                agent=username,
                llm_calls=llm_calls,
            )
    return (results, llm_calls)


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
    parser.add_argument("--run-id", type=int, default=None)
    parser.add_argument("--app-db", default=None)
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)

    asyncio.run(
        run_simulation(
            post_path=args.post,
            profiles_path=args.profiles,
            tag=args.tag,
            results_dir=args.results_dir,
            run_id=args.run_id,
            app_db_path=args.app_db,
        )
    )


if __name__ == "__main__":
    main()
