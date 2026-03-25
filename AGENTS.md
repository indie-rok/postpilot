# PROJECT KNOWLEDGE BASE

**Generated:** 2026-03-25
**Commit:** 29a6353
**Branch:** main

## OVERVIEW

Post Pilot: npm-distributed CLI wrapping a Python backend. Users run `npx post-pilot init` in their SaaS project to simulate Reddit community reactions to launch posts using CAMEL-AI's OASIS multi-agent framework. Node.js manages venv lifecycle, Python does all logic.

## STRUCTURE

```
postpilot/
├── bin/post-pilot.js           # Node CLI — finds Python 3.11, creates venv, spawns Python
├── simulation/                 # Python backend (ALL business logic lives here)
│   ├── cli.py                  # Command router: init | configure | learn | serve
│   ├── server.py               # FastAPI — 22 REST endpoints + WebSocket + SPA
│   ├── db.py                   # SQLite CRUD — 8 tables, path resolution
│   ├── scanner.py              # Repo discovery → LLM context → product profile
│   ├── env_writer.py           # Credential file writer
│   ├── scripts/                # Simulation pipeline (see scripts/AGENTS.md)
│   ├── config/                 # 8 archetype definitions, time/activity params
│   ├── prompts/                # LLM prompt templates (9 modules)
│   ├── profiles/               # Persona JSON (ships r_saas_community.json)
│   ├── static/index.html       # Single-file SPA (2.2K lines, vanilla JS, dark theme)
│   └── tests/                  # pytest suite (15 modules, NOT published to npm)
├── package.json                # npm manifest — negation patterns exclude dev artifacts
└── CLAUDE.md                   # Architecture guide (canonical reference)
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| CLI commands | `simulation/cli.py` | `cmd_init`, `cmd_configure`, `cmd_learn`, `cmd_serve` |
| API endpoints | `simulation/server.py` | 22 routes; `SimulationCoordinator` manages WebSocket |
| Database schema | `simulation/db.py:SCHEMA_SQL` | 8 tables; `_user_project_dir()` for path resolution |
| Simulation execution | `simulation/scripts/run_simulation.py` | OASIS orchestration, spawned as subprocess |
| Post grading | `simulation/scripts/generate_scorecard.py` | Grade formula, LLM classification, 15+ metrics |
| Persona generation | `simulation/scripts/generate_community.py` | Reddit scraping via PRAW + LLM persona generation |
| Product scanning | `simulation/scanner.py` | File discovery → LLM context building |
| LLM prompts | `simulation/prompts/` | One module per feature (scorecard, rewrite, humanizer, etc.) |
| Frontend UI | `simulation/static/index.html` | 4 views: setup → dashboard → simulate → results |
| Archetype config | `simulation/config/simulation_config.py` | 8 personas, time multipliers, activity levels |

## CRITICAL: TWO-DIRECTORY ARCHITECTURE

```
User's Project Dir (writable)          npm Package Dir (READ-ONLY after install)
├── .post-pilot/                       ├── bin/post-pilot.js
│   ├── .env          (credentials)    └── simulation/
│   ├── post-pilot.db (SQLite)             ├── cli.py, server.py, db.py ...
│   └── .venv/        (Python env)         └── (source code)
└── (user's source code)
```

**Bridge:** `POST_PILOT_PROJECT_DIR` env var (set by Node wrapper) tells Python where user data lives. Both `db.py:_user_project_dir()` and `cli.py:_user_cwd()` read this var.

## CONVENTIONS

- **Lazy imports in cli.py** — `__import__()` defers openai/praw/camel loading until needed. Keeps `--help` fast.
- **No npm lifecycle scripts** — No build step, no postinstall. Package ships Python source as-is.
- **Single-file SPA** — No React/Vue/build pipeline. Vanilla JS served by FastAPI's StaticFiles.
- **Subprocess stdout protocol** — Simulation emits `PROGRESS:{json}` lines; server parses and broadcasts via WebSocket.
- **npm `files` negation** — `!simulation/.venv`, `!simulation/tests`, etc. Published package is ~300KB.
- **Pyright directives** — `reportMissingImports=false` at top of Python files (dynamic imports).

## ANTI-PATTERNS (THIS PROJECT)

- **NEVER write files to `simulation/` dir** — may be read-only in npm cache. Use `get_project_dir()`.
- **NEVER create venv inside package dir** — always at `<user-project>/.post-pilot/.venv`.
- **NEVER insert multiple rows in `product` table** — `CHECK(id=1)` constraint.
- **NEVER modify `run_agent` records** — immutable by design (audit trail).
- **NEVER store credentials in DB** — always in `.post-pilot/.env`.
- **NEVER delete `scripts/__init__.py`** — server.py imports scripts as package.
- **NEVER import heavy deps at module level in cli.py** — use lazy `__import__()`.
- **NEVER change subprocess cwd** — must be `BASE_DIR` (simulation dir) for imports to resolve.

## COMMANDS

```bash
# Python tests
cd simulation && python -m pytest tests/
cd simulation && python -m pytest tests/test_db.py -v

# Verify npm package contents
npm pack --dry-run

# Run CLI locally (from another project)
node /path/to/postpilot/bin/post-pilot.js init
node /path/to/postpilot/bin/post-pilot.js serve --port 8000

# Dev server (skip Node wrapper)
cd simulation
POST_PILOT_PROJECT_DIR=/path/to/test/project python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

## NOTES

- **Python 3.11 required exactly** — CAMEL-OASIS doesn't support 3.12+. `bin/post-pilot.js` enforces this.
- **No CI/CD** — Manual `npm publish`. No GitHub Actions, no pre-commit hooks.
- **No linter/formatter configured** — No ESLint, Prettier, Black, or Ruff configs.
- **Temp files** (`run_profiles.json`, `run_post.txt`) written to user's `.post-pilot/` during simulation.
- **Default LLM** — OpenRouter (`gpt-4o-mini`). Any OpenAI-compatible API works.
- **Database** — 8 tables: `product` (single row), `community`, `community_profile`, `run`, `run_agent`, `run_comment`, `run_interview`, `run_scorecard`. Full DDL in `db.py:SCHEMA_SQL`.
