# simulation/ — Python Backend

All business logic lives here. Node.js CLI (`bin/post-pilot.js`) spawns Python with `PYTHONPATH=simulation/` and `POST_PILOT_PROJECT_DIR=<user-cwd>`.

## MODULE MAP

| Module | Lines | Role |
|--------|-------|------|
| `cli.py` | 395 | Command router — `cmd_init`, `cmd_configure`, `cmd_learn`, `cmd_serve` |
| `server.py` | 745 | FastAPI — 22 REST endpoints, WebSocket progress, `SimulationCoordinator` |
| `db.py` | 933 | SQLite — 8-table schema, all CRUD, path resolution via `_user_project_dir()` |
| `scanner.py` | 174 | Scans user repo → builds LLM context → generates product profile |
| `env_writer.py` | 22 | Writes credentials to `.post-pilot/.env` |
| `__main__.py` | 2 | Module entry: `from cli import main; main()` |

## SUBDIRECTORIES

| Dir | Purpose | Details |
|-----|---------|---------|
| `scripts/` | Simulation pipeline | 9 modules — orchestration, grading, rewriting. See `scripts/AGENTS.md` |
| `prompts/` | LLM prompt templates | 9 modules — one per feature (scorecard, rewrite, humanizer, suggest, etc.) |
| `config/` | Simulation params | 8 archetypes, time multipliers, peak/off-peak hours, activity levels |
| `profiles/` | Persona JSON | Ships `r_saas_community.json` (18 pre-built personas for r/SaaS) |
| `static/` | Frontend SPA | Single `index.html` (2.2K lines vanilla JS). 4 views: setup→dashboard→simulate→results |
| `tests/` | pytest suite | 15 modules, ~2.2K lines. NOT published to npm |
| `posts/` | Post content | `run_post.txt` — temp file during simulation |

## PATH RESOLUTION (CRITICAL)

Every module needing user data MUST read `POST_PILOT_PROJECT_DIR`:
- `db.py:_user_project_dir()` → returns user's project root
- `db.py:get_project_dir()` → returns `.post-pilot/` subdir
- `cli.py:_user_cwd()` → same logic for CLI commands

**NEVER use `Path.cwd()` directly** — it resolves to the npm cache, not user's project.

## SERVER ARCHITECTURE

`SimulationCoordinator` (server.py lines 116-263):
- Singleton managing WebSocket clients and active simulation
- Spawns `run_simulation.py` as subprocess via `RUNNER_WRAPPER` (inline Python string)
- Parses stdout `PROGRESS:{json}` lines → broadcasts via WebSocket
- Prevents concurrent simulations with `_state_lock`
- Applies/restores LLM env vars per-request

**Endpoint groups:** simulate (3), scorecard/analyze (3), communities CRUD (6), product CRUD (3), system (4), SPA catch-all (1), thread (1), suggest (1).

## DATABASE

8 tables in `db.py:SCHEMA_SQL`:
- `product` — Single row (`CHECK(id=1)`). Name, description, features, audience.
- `community` — Subreddit-based groups. Name, description.
- `community_profile` — Personas with archetype, bio, interests, writing style.
- `run` — Simulation runs. Tag, status, post content, config.
- `run_agent` — Denormalized agent snapshot per run (immutable).
- `run_comment` — Extracted comments with sentiment.
- `run_interview` — Post-simulation agent interviews.
- `run_scorecard` — Cached scorecard JSON.

## TESTING

```bash
python -m pytest tests/                    # All tests
python -m pytest tests/test_db.py -v       # Single module
```

- Framework: pytest 8.0+ with pytest-asyncio
- No `conftest.py` — fixtures defined per-test-module
- Mocking: `monkeypatch.setattr()` on internal helpers (`_ask_llm`, `_ask_humanizer`)
- DB fixtures: `tempfile.mkstemp(suffix=".db")` with manual cleanup
- Naming: `test_<module>_<scenario>()` — function-based, no classes

## CONVENTIONS UNIQUE TO THIS DIR

- **Pyright directives** at top of files: `reportMissingImports=false`, `reportAny=false`
- **sys.path manipulation** in tests: `sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))`
- **LLM model creation** pattern repeated across scripts — `ModelFactory.create()` with OpenAI-compatible config
- **JSON from LLM** — all modules strip markdown code fences before `json.loads()`
- **dotenv loading** — `load_dotenv()` from parent `.env` at module level in scripts
