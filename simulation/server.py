import asyncio
import json
import os
import random
import sys
from pathlib import Path
from typing import Callable, TypedDict, cast

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import scripts.analyze_and_rewrite as analyze_module
import scripts.generate_html as generate_html_module
import scripts.generate_scorecard as scorecard_module


JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | dict[str, "JsonValue"] | list["JsonValue"]
JsonDict = dict[str, JsonValue]


class Profile(TypedDict, total=False):
    username: str
    realname: str
    bio: str
    persona: str
    age: int
    gender: str
    mbti: str
    country: str
    profession: str
    interested_topics: list[str]


BASE_DIR = Path(__file__).resolve().parent
PROFILES_DIR = BASE_DIR / "profiles"
POSTS_DIR = BASE_DIR / "posts"
RESULTS_DIR = BASE_DIR / "results"
STATIC_DIR = BASE_DIR / "static"

ALL_PROFILES_PATH = PROFILES_DIR / "r_saas_community.json"
RUN_PROFILES_PATH = PROFILES_DIR / "run_profiles.json"
RUN_POST_PATH = POSTS_DIR / "run_post.txt"

RUN_TAG = "run"

analyze_comments: Callable[[list[dict[str, str]]], str] = cast(
    Callable[[list[dict[str, str]]], str], analyze_module.analyze
)
fetch_comments: Callable[[str], list[dict[str, str]]] = cast(
    Callable[[str], list[dict[str, str]]], analyze_module.get_comments
)
fetch_original_post: Callable[[str], str] = cast(
    Callable[[str], str], analyze_module.get_original_post
)
rewrite_post: Callable[[str, str], str] = cast(
    Callable[[str, str], str], analyze_module.rewrite
)
extract_sim_data: Callable[[str, str], JsonDict] = cast(
    Callable[[str, str], JsonDict], generate_html_module.extract_data
)
THREAD_TEMPLATE: str = cast(str, generate_html_module.TEMPLATE)

_ = load_dotenv(BASE_DIR / ".env")


class LLMConfig(BaseModel):
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""


class SimulateRequest(BaseModel):
    agent_count: int = Field(ge=2, le=18)
    total_hours: int = Field(ge=1, le=72)
    post_content: str = Field(min_length=1)
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""


class SimulationCoordinator:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._clients_lock: asyncio.Lock = asyncio.Lock()
        self._state_lock: asyncio.Lock = asyncio.Lock()
        self._current_task: asyncio.Task[None] | None = None
        self._llm_config: LLMConfig = LLMConfig()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._clients_lock:
            self._clients.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._clients_lock:
            self._clients.discard(websocket)

    async def broadcast(self, payload: JsonDict) -> None:
        async with self._clients_lock:
            clients = list(self._clients)

        stale: list[WebSocket] = []
        for client in clients:
            try:
                await client.send_json(payload)
            except Exception:
                stale.append(client)

        if stale:
            async with self._clients_lock:
                for client in stale:
                    self._clients.discard(client)

    async def start(self, request: SimulateRequest) -> str:
        async with self._state_lock:
            if self._current_task and not self._current_task.done():
                raise HTTPException(
                    status_code=409,
                    detail="A simulation is already running. Wait for completion.",
                )
            self._llm_config = LLMConfig(
                llm_api_key=request.llm_api_key,
                llm_base_url=request.llm_base_url,
                llm_model=request.llm_model,
            )
            self._current_task = asyncio.create_task(self._run(request))

        return RUN_TAG

    async def _run(self, request: SimulateRequest) -> None:
        try:
            selected = select_diverse_profiles(request.agent_count, ALL_PROFILES_PATH)
            _ = RUN_PROFILES_PATH.write_text(
                json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            _ = RUN_POST_PATH.write_text(
                request.post_content.strip() + "\n", encoding="utf-8"
            )
            cleanup_previous_run(RUN_TAG)

            await self.broadcast(
                {
                    "type": "log",
                    "message": (
                        f"Prepared run with {request.agent_count} agents for "
                        f"{request.total_hours} simulated hour(s)."
                    ),
                }
            )

            run_env = os.environ.copy()
            if request.llm_api_key:
                run_env["LLM_API_KEY"] = request.llm_api_key
            if request.llm_base_url:
                run_env["LLM_BASE_URL"] = request.llm_base_url
            if request.llm_model:
                run_env["LLM_MODEL"] = request.llm_model

            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                RUNNER_WRAPPER,
                "--post",
                str(RUN_POST_PATH.relative_to(BASE_DIR)),
                "--tag",
                RUN_TAG,
                "--profiles",
                str(RUN_PROFILES_PATH.relative_to(BASE_DIR)),
                "--total-hours",
                str(request.total_hours),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(BASE_DIR),
                env=run_env,
            )

            assert process.stdout is not None
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                msg = line.decode("utf-8", errors="replace").rstrip()
                if msg:
                    await self.broadcast({"type": "log", "message": msg})

            return_code = await process.wait()
            if return_code == 0:
                await self.broadcast({"type": "done", "tag": RUN_TAG})
            else:
                await self.broadcast(
                    {
                        "type": "error",
                        "message": f"Simulation process exited with code {return_code}",
                    }
                )
        except Exception as exc:
            await self.broadcast({"type": "error", "message": str(exc)})


RUNNER_WRAPPER = r"""
import argparse
import runpy
import sys

from config import simulation_config as simulation_config


parser = argparse.ArgumentParser()
parser.add_argument("--post", required=True)
parser.add_argument("--tag", required=True)
parser.add_argument("--profiles", required=True)
parser.add_argument("--total-hours", required=True, type=int)
args = parser.parse_args()

simulation_config.TIME_CONFIG = dict(simulation_config.TIME_CONFIG)
simulation_config.TIME_CONFIG["total_hours"] = args.total_hours

sys.argv = [
    "scripts/run_simulation.py",
    "--post",
    args.post,
    "--tag",
    args.tag,
    "--profiles",
    args.profiles,
]
runpy.run_path("scripts/run_simulation.py", run_name="__main__")
"""


def _archetype(username: str) -> str:
    if "skeptic" in username:
        return "skeptic"
    if "founder_" in username:
        return "founder"
    if "indie" in username:
        return "indie"
    if "hr_" in username:
        return "hr"
    if "lurker" in username:
        return "lurker"
    if "regular" in username:
        return "regular"
    if "vc_" in username:
        return "vc"
    return "other"


def select_diverse_profiles(agent_count: int, profiles_path: Path) -> list[Profile]:
    profiles = cast(
        list[Profile], json.loads(profiles_path.read_text(encoding="utf-8"))
    )
    by_archetype: dict[str, list[Profile]] = {}
    for profile in profiles:
        kind = _archetype(profile.get("username", ""))
        by_archetype.setdefault(kind, []).append(profile)

    rng = random.SystemRandom()
    for items in by_archetype.values():
        rng.shuffle(items)

    chosen: list[Profile] = []

    skeptics = by_archetype.get("skeptic", [])
    founders = by_archetype.get("founder", [])
    if not skeptics or not founders:
        raise RuntimeError("Profiles must include at least one skeptic and one founder")

    chosen.append(skeptics.pop(0))
    if len(chosen) < agent_count:
        chosen.append(founders.pop(0))

    rotation = [
        "founder",
        "skeptic",
        "indie",
        "hr",
        "regular",
        "vc",
        "lurker",
        "other",
    ]
    idx = 0
    while len(chosen) < agent_count:
        archetype = rotation[idx % len(rotation)]
        idx += 1
        pool = by_archetype.get(archetype, [])
        if not pool:
            if all(not by_archetype.get(name, []) for name in rotation):
                break
            continue
        chosen.append(pool.pop(0))

    if len(chosen) < agent_count:
        raise RuntimeError(
            f"Unable to pick {agent_count} profiles from available archetypes"
        )

    return chosen


def cleanup_previous_run(tag: str) -> None:
    targets = [
        RESULTS_DIR / f"{tag}.db",
        RESULTS_DIR / f"{tag}-thread.html",
        RESULTS_DIR / "analysis.md",
        RESULTS_DIR / "improved-post.md",
    ]
    for target in targets:
        if target.exists():
            _ = target.unlink()


def resolve_profiles_for_tag(tag: str) -> Path:
    if tag == RUN_TAG and RUN_PROFILES_PATH.exists():
        return RUN_PROFILES_PATH
    return ALL_PROFILES_PATH


coordinator = SimulationCoordinator()

app = FastAPI(title="Reddit Simulation API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/simulate")
async def simulate(request: SimulateRequest) -> dict[str, str]:
    tag = await coordinator.start(request)
    return {"status": "started", "tag": tag}


@app.websocket("/ws/progress")
async def progress_socket(websocket: WebSocket) -> None:
    await coordinator.connect(websocket)
    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        await coordinator.disconnect(websocket)


@app.get("/api/results/{tag}")
async def get_results(tag: str):
    db_path = RESULTS_DIR / f"{tag}.db"
    if not db_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Results not found for tag '{tag}'"
        )

    profiles_path = resolve_profiles_for_tag(tag)
    data = extract_sim_data(str(db_path), str(profiles_path))
    return JSONResponse(content=data)


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


@app.post("/api/analyze/{tag}")
async def analyze_tag(tag: str) -> dict[str, str]:
    db_path = RESULTS_DIR / f"{tag}.db"
    if not db_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Results not found for tag '{tag}'"
        )

    saved = _apply_llm_config(coordinator._llm_config)
    try:
        comments = await asyncio.to_thread(fetch_comments, str(db_path))
        if not comments:
            raise HTTPException(status_code=400, detail="No comments found to analyze")
        original_post = await asyncio.to_thread(fetch_original_post, str(db_path))
        analysis = await asyncio.to_thread(analyze_comments, comments)
        improved_post = await asyncio.to_thread(rewrite_post, original_post, analysis)
    finally:
        _restore_env(saved)

    return {"analysis": analysis, "improved_post": improved_post}


@app.post("/api/scorecard/{tag}")
async def get_scorecard(tag: str):
    db_path = RESULTS_DIR / f"{tag}.db"
    if not db_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Results not found for tag '{tag}'"
        )

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
        raise HTTPException(
            status_code=404, detail=f"Results not found for tag '{tag}'"
        )

    saved = _apply_llm_config(coordinator._llm_config)
    try:
        original_post = await asyncio.to_thread(fetch_original_post, str(db_path))
        profiles_path = resolve_profiles_for_tag(tag)
        scorecard = await asyncio.to_thread(
            scorecard_module.generate_scorecard, str(db_path), str(profiles_path)
        )
        analysis_context = json.dumps(scorecard, indent=2, default=str)
        improved_post = await asyncio.to_thread(
            rewrite_post, original_post, analysis_context
        )
    finally:
        _restore_env(saved)

    return {"improved_post": improved_post}


@app.get("/api/thread/{tag}", response_class=HTMLResponse)
async def get_thread(tag: str) -> HTMLResponse:
    db_path = RESULTS_DIR / f"{tag}.db"
    if not db_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Results not found for tag '{tag}'"
        )

    profiles_path = resolve_profiles_for_tag(tag)
    data = extract_sim_data(str(db_path), str(profiles_path))
    html = THREAD_TEMPLATE.replace(
        "__DATA__", json.dumps(data, indent=2, ensure_ascii=False, default=str)
    )
    return HTMLResponse(content=html)


app.mount(
    "/",
    StaticFiles(directory=str(STATIC_DIR), html=True, check_dir=False),
    name="static",
)
