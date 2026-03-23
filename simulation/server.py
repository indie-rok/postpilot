# pyright: reportMissingImports=false, reportImplicitRelativeImport=false

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, TypedDict, cast

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import scripts.analyze_and_rewrite as analyze_module
import scripts.generate_html as generate_html_module
import scripts.generate_scorecard as scorecard_module
from db import (
    create_run,
    create_run_agents,
    delete_community,
    delete_profile,
    delete_run,
    get_all_profiles_for_community,
    get_community_by_subreddit,
    get_connection,
    get_product,
    get_results_for_run,
    init_db,
    list_communities,
    list_runs,
    save_product,
    seed_default_community,
    select_profiles_for_community,
    update_profile,
)


JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | dict[str, "JsonValue"] | list["JsonValue"]
JsonDict = dict[str, JsonValue]


class Profile(TypedDict, total=False):
    username: str
    realname: str
    archetype: str
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
APP_DB = str(BASE_DIR / "reddit-sim.db")

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
    community_id: int = 1
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""


import re

_ALLOWED_LOG_RE = re.compile(
    r"^(Preparing simulation|"
    r"\d+ agents loaded|"
    r"Environment ready|"
    r"Post published by |"
    r"Hour \d+/\d+|"
    r"\d+ agents responding|"
    r"Simulation complete|"
    r"Interviewing agents|"
    r"Interviewed .+ ✓|"
    r"Skipped \d+ inactive|"
    r"\d+ interviews complete|"
    r"Interview failed:)"
)


class SimulationCoordinator:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._clients_lock: asyncio.Lock = asyncio.Lock()
        self._state_lock: asyncio.Lock = asyncio.Lock()
        self._current_task: asyncio.Task[None] | None = None
        self._llm_config: LLMConfig = LLMConfig()
        self._current_run_id: int | None = None
        self._current_tag: str | None = None

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
        tag = f"run_{uuid.uuid4().hex[:8]}"
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
            self._current_task = asyncio.create_task(self._run(request, tag))

        return tag

    async def _run(self, request: SimulateRequest, tag: str) -> None:
        try:
            selected_profiles = select_profiles_for_community(
                APP_DB, request.community_id, request.agent_count
            )
            run_id = create_run(
                APP_DB,
                tag,
                request.community_id,
                request.post_content,
                request.agent_count,
                request.total_hours,
                request.llm_model or None,
            )
            _ = create_run_agents(APP_DB, run_id, selected_profiles)
            self._current_run_id = run_id
            self._current_tag = tag

            selected: list[Profile] = [
                _profile_for_runner(profile) for profile in selected_profiles
            ]
            _ = RUN_PROFILES_PATH.write_text(
                json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            _ = RUN_POST_PATH.write_text(
                request.post_content.strip() + "\n", encoding="utf-8"
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
                tag,
                "--profiles",
                str(RUN_PROFILES_PATH.relative_to(BASE_DIR)),
                "--total-hours",
                str(request.total_hours),
                "--run-id",
                str(run_id),
                "--app-db",
                APP_DB,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(BASE_DIR),
                env=run_env,
                limit=1024 * 1024,
            )

            assert process.stdout is not None
            while True:
                try:
                    line = await process.stdout.readline()
                except (ValueError, asyncio.LimitOverrunError):
                    while True:
                        chunk = await process.stdout.read(65536)
                        if not chunk or b"\n" in chunk:
                            break
                    continue
                if not line:
                    break
                msg = line.decode("utf-8", errors="replace").rstrip()
                if msg:
                    if msg.startswith("PROGRESS:"):
                        try:
                            progress_data = json.loads(msg[9:])
                            progress_data["type"] = "progress"
                            await self.broadcast(progress_data)
                        except json.JSONDecodeError:
                            pass
                    elif _ALLOWED_LOG_RE.match(msg):
                        await self.broadcast({"type": "log", "message": msg})

            return_code = await process.wait()
            if return_code == 0:
                await self.broadcast({"type": "done", "tag": self._current_tag})
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
parser.add_argument("--run-id", type=int, default=None)
parser.add_argument("--app-db", default=None)
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
if args.run_id is not None:
    sys.argv += ["--run-id", str(args.run_id)]
if args.app_db is not None:
    sys.argv += ["--app-db", args.app_db]
runpy.run_path("scripts/run_simulation.py", run_name="__main__")
"""


def _profile_for_runner(profile: dict[str, Any]) -> Profile:
    demographics: dict[str, Any] = {}
    raw_demographics = profile.get("demographics")
    if isinstance(raw_demographics, str):
        try:
            parsed = json.loads(raw_demographics)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            demographics = parsed
    elif isinstance(raw_demographics, dict):
        demographics = raw_demographics

    runner_profile: Profile = {
        "username": str(profile.get("username", "")),
        "realname": str(profile.get("realname", "")),
        "archetype": str(profile.get("archetype", "Community Regular")),
        "bio": str(profile.get("bio") or ""),
        "persona": str(profile.get("persona", "")),
    }

    age = demographics.get("age")
    if isinstance(age, int):
        runner_profile["age"] = age

    for key in ["gender", "mbti", "country", "profession"]:
        value = demographics.get(key)
        if isinstance(value, str) and value:
            runner_profile[key] = value

    topics = demographics.get("interested_topics")
    if isinstance(topics, list):
        runner_profile["interested_topics"] = [
            topic for topic in topics if isinstance(topic, str)
        ]

    return runner_profile


coordinator = SimulationCoordinator()

app = FastAPI(title="Reddit Simulation API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_init_db() -> None:
    init_db(APP_DB)
    seed_default_community(APP_DB, str(ALL_PROFILES_PATH))


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
    conn = get_connection(APP_DB)
    try:
        row = conn.execute("SELECT id FROM run WHERE tag = ?", (tag,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Run not found: {tag}")
    data = get_results_for_run(APP_DB, int(row["id"]))
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
    conn = get_connection(APP_DB)
    try:
        run_row = conn.execute(
            "SELECT id, post_content FROM run WHERE tag = ?", (tag,)
        ).fetchone()
    finally:
        conn.close()
    if not run_row:
        raise HTTPException(status_code=404, detail=f"Run not found: {tag}")
    run_id = run_row["id"]

    # Get comments from app DB
    conn = get_connection(APP_DB)
    try:
        rows = conn.execute(
            "SELECT c.content, a.realname AS author FROM run_comment c JOIN run_agent a ON c.agent_id = a.id WHERE c.run_id = ?",
            (run_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        raise HTTPException(status_code=400, detail="No comments found to analyze")

    comments = [{"content": row["content"], "author": row["author"]} for row in rows]
    original_post = run_row["post_content"]

    saved = _apply_llm_config(coordinator._llm_config)
    try:
        analysis = await asyncio.to_thread(analyze_module.analyze, comments)
        improved_post = await asyncio.to_thread(
            analyze_module.rewrite, original_post, analysis
        )
    finally:
        _restore_env(saved)

    return {"analysis": analysis, "improved_post": improved_post}


class BatchConfig(BaseModel):
    batch_size: int = 0


@app.post("/api/scorecard/{tag}")
async def get_scorecard(tag: str, config: BatchConfig = BatchConfig()):
    conn = get_connection(APP_DB)
    try:
        run_row = conn.execute("SELECT id FROM run WHERE tag = ?", (tag,)).fetchone()
    finally:
        conn.close()
    if not run_row:
        raise HTTPException(status_code=404, detail=f"Run not found: {tag}")
    run_id = int(run_row["id"])

    conn = get_connection(APP_DB)
    try:
        cached = conn.execute(
            "SELECT data FROM run_scorecard WHERE run_id = ?", (run_id,)
        ).fetchone()
    finally:
        conn.close()
    if cached:
        return JSONResponse(content=json.loads(str(cached["data"])))

    saved = _apply_llm_config(coordinator._llm_config)
    try:
        result = await asyncio.to_thread(
            scorecard_module.generate_scorecard,
            APP_DB,
            run_id,
            batch_size=config.batch_size,
        )
    finally:
        _restore_env(saved)

    return JSONResponse(content=result)


@app.post("/api/rewrite/{tag}")
async def rewrite_post_endpoint(
    tag: str, config: BatchConfig = BatchConfig()
) -> dict[str, str]:
    conn = get_connection(APP_DB)
    try:
        run_row = conn.execute(
            "SELECT id, post_content FROM run WHERE tag = ?", (tag,)
        ).fetchone()
    finally:
        conn.close()
    if not run_row:
        raise HTTPException(status_code=404, detail=f"Run not found: {tag}")
    run_id = int(run_row["id"])
    original_post = str(run_row["post_content"])

    saved = _apply_llm_config(coordinator._llm_config)
    try:
        scorecard = await asyncio.to_thread(
            scorecard_module.generate_scorecard,
            APP_DB,
            run_id,
            batch_size=config.batch_size,
        )
        analysis_context = json.dumps(scorecard, indent=2, default=str)
        improved_post = await asyncio.to_thread(
            analyze_module.rewrite, original_post, analysis_context
        )
    finally:
        _restore_env(saved)

    return {"improved_post": improved_post}


@app.get("/api/reddit-status")
async def reddit_status() -> dict[str, Any]:
    has_keys = bool(os.getenv("REDDIT_CLIENT_ID") and os.getenv("REDDIT_CLIENT_SECRET"))
    return {"configured": has_keys}


class GenerateCommunityRequest(BaseModel):
    subreddit: str = Field(min_length=1)
    persona_count: int = Field(ge=3, le=30, default=18)


@app.post("/api/communities/generate")
async def generate_community_endpoint(
    request: GenerateCommunityRequest,
) -> JSONResponse:
    import scripts.generate_community as gen_module

    saved = _apply_llm_config(coordinator._llm_config)
    try:
        community_id, personas = await asyncio.to_thread(
            gen_module.generate_community,
            request.subreddit,
            request.persona_count,
            APP_DB,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        _restore_env(saved)

    profiles = get_all_profiles_for_community(APP_DB, community_id)
    return JSONResponse(
        content={
            "community_id": community_id,
            "subreddit": request.subreddit,
            "profile_count": len(profiles),
            "profiles": profiles,
        }
    )


@app.get("/api/communities")
async def get_communities() -> JSONResponse:
    communities = list_communities(APP_DB)
    return JSONResponse(content=communities)


@app.get("/api/communities/{community_id}/profiles")
async def get_community_profiles(community_id: int) -> JSONResponse:
    profiles = get_all_profiles_for_community(APP_DB, community_id)
    return JSONResponse(content=profiles)


class UpdateProfileRequest(BaseModel):
    username: str | None = None
    realname: str | None = None
    archetype: str | None = None
    bio: str | None = None
    persona: str | None = None


@app.put("/api/communities/profiles/{profile_id}")
async def update_profile_endpoint(
    profile_id: int, request: UpdateProfileRequest
) -> dict[str, str]:
    fields = {k: v for k, v in request.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    update_profile(APP_DB, profile_id, fields)
    return {"status": "updated"}


@app.delete("/api/communities/profiles/{profile_id}")
async def delete_profile_endpoint(profile_id: int) -> dict[str, str]:
    delete_profile(APP_DB, profile_id)
    return {"status": "deleted"}


@app.delete("/api/communities/{community_id}")
async def delete_community_endpoint(community_id: int) -> dict[str, str]:
    delete_community(APP_DB, community_id)
    return {"status": "deleted"}


@app.get("/api/company-md")
async def get_company_md() -> dict[str, Any]:
    cwd = Path.cwd()
    md_path = cwd / "company.md"
    if not md_path.exists():
        md_path = cwd.parent / "company.md"
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="No company.md found")
    content = md_path.read_text(encoding="utf-8")
    name = ""
    tagline = ""
    for line in content.splitlines():
        stripped = line.strip()
        if not name and stripped.startswith("# "):
            name = stripped[2:].strip()
        elif name and not tagline and stripped and not stripped.startswith("#"):
            tagline = stripped
            break
    return {"content": content, "name": name, "tagline": tagline}


@app.post("/api/suggest-post/{community_id}")
async def suggest_post(community_id: int) -> dict[str, str]:
    import scripts.generate_community as gen_module

    product = get_product(APP_DB)
    if not product:
        raise HTTPException(status_code=400, detail="No product configured")

    community = None
    for c in list_communities(APP_DB):
        if c["id"] == community_id:
            community = c
            break
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")

    company_md = ""
    cwd = Path.cwd()
    md_path = cwd / "company.md"
    if not md_path.exists():
        md_path = cwd.parent / "company.md"
    if md_path.exists():
        company_md = md_path.read_text(encoding="utf-8")

    profiles = get_all_profiles_for_community(APP_DB, community_id)
    archetypes = set(p["archetype"] for p in profiles)

    prompt = f"""Write a compelling Reddit launch post for the subreddit {community["subreddit"]}.

PRODUCT INFO:
{company_md or product.get("description", product.get("name", "Unknown product"))}

COMMUNITY PERSONAS ({len(profiles)} members):
Archetypes: {", ".join(sorted(archetypes))}

Write the post as if you are the founder/maker posting in {community["subreddit"]}. Make it:
- Authentic and conversational (not salesy)
- Include specific metrics, numbers, or learnings if available from the product info
- Ask 2-3 genuine questions to spark discussion
- Match the tone of {community["subreddit"]}
- Address concerns that the community archetypes would likely raise
- Keep it under 500 words

Return ONLY the post text, no title prefix, no markdown formatting."""

    saved = _apply_llm_config(coordinator._llm_config)
    try:
        content = await asyncio.to_thread(
            gen_module._ask_llm, "You write authentic Reddit launch posts.", prompt
        )
    finally:
        _restore_env(saved)

    return {"content": content}


class ProductRequest(BaseModel):
    name: str = Field(min_length=1)
    tagline: str | None = None
    description: str | None = None
    features: str | None = None
    pricing: str | None = None
    target_audience: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    batch_size: int = 0


@app.get("/api/product")
async def get_product_endpoint() -> JSONResponse:
    product = get_product(APP_DB)
    if product is None:
        raise HTTPException(status_code=404, detail="No product configured")
    return JSONResponse(content=product)


@app.post("/api/product")
async def save_product_endpoint(request: ProductRequest) -> dict[str, str]:
    save_product(APP_DB, request.model_dump())
    return {"status": "saved"}


@app.get("/api/runs")
async def get_runs(community_id: int | None = None) -> JSONResponse:
    runs = list_runs(APP_DB, community_id=community_id)
    return JSONResponse(content=runs)


@app.delete("/api/runs/{tag}")
async def delete_run_endpoint(tag: str) -> dict[str, str]:
    conn = get_connection(APP_DB)
    try:
        row = conn.execute("SELECT id FROM run WHERE tag = ?", (tag,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Run not found: {tag}")
    delete_run(APP_DB, int(row["id"]))
    return {"status": "deleted"}


@app.get("/api/thread/{tag}", response_class=HTMLResponse)
async def get_thread(tag: str) -> HTMLResponse:
    conn = get_connection(APP_DB)
    try:
        row = conn.execute("SELECT id FROM run WHERE tag = ?", (tag,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Run not found: {tag}")
    data = get_results_for_run(APP_DB, int(row["id"]))
    html = THREAD_TEMPLATE.replace(
        "__DATA__", json.dumps(data, indent=2, ensure_ascii=False, default=str)
    )
    return HTMLResponse(content=html)


app.mount(
    "/static", StaticFiles(directory=str(STATIC_DIR), check_dir=False), name="static"
)


@app.get("/{path:path}")
async def spa_catch_all(path: str) -> HTMLResponse:
    index_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
