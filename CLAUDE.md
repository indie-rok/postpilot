# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Post Pilot is an npm-distributed CLI tool that wraps a Python backend. Users run `npx post-pilot init` in their SaaS project to test Reddit launch posts against AI community personas before posting. The simulation uses CAMEL-AI's OASIS framework to run multi-agent LLM conversations.

## Architecture

**Two-language design:** Node.js CLI wrapper (`bin/post-pilot.js`) manages Python venv lifecycle, then delegates all logic to the Python backend (`simulation/`).

```
npx post-pilot <command>
  → bin/post-pilot.js (finds Python 3.11+, creates .post-pilot/.venv, installs deps)
    → python -m cli <command> (with PYTHONPATH=simulation/, POST_PILOT_PROJECT_DIR=cwd)
      → cli.py routes to: init | configure | learn | serve
```

**Path resolution is critical:** All user data (`.post-pilot/.env`, `.post-pilot/post-pilot.db`) resolves relative to the user's working directory via `POST_PILOT_PROJECT_DIR` env var — NOT the npm package install directory. The Python source code lives in the npm package's `simulation/` dir (read-only after install). `db.py:_user_project_dir()` and `cli.py:_user_cwd()` both read this env var.

**Data storage:** Credentials in `.post-pilot/.env` (not in DB). SQLite DB at `.post-pilot/post-pilot.db`. Single-row product table (id=1 CHECK constraint). Run history denormalizes agent data into `run_agent` so it's immutable.

**Web server:** `server.py` is a FastAPI app. Simulation progress streams via WebSocket (`PROGRESS:{json}` on stdout → `/ws/progress`). Static SPA at `simulation/static/index.html` (vanilla JS, no framework).

## Commands

**Run Python tests:**
```bash
cd simulation && python -m pytest tests/
# Single test:
cd simulation && python -m pytest tests/test_db.py -v
```

**Check what npm would publish:**
```bash
npm pack --dry-run
```

**Run the CLI locally (from another project dir):**
```bash
node /path/to/bot2/bin/post-pilot.js init
node /path/to/bot2/bin/post-pilot.js serve --port 8000
```

**Start dev server directly (skip Node wrapper):**
```bash
cd simulation
POST_PILOT_PROJECT_DIR=/path/to/test/project python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

## Key Files

| File | Role |
|------|------|
| `bin/post-pilot.js` | npm entry point — venv management, Python spawning |
| `simulation/cli.py` | Command router (init/configure/learn/serve), interactive prompts, Spinner class |
| `simulation/server.py` | FastAPI app — REST + WebSocket endpoints, simulation coordinator |
| `simulation/db.py` | SQLite schema (8 tables), all CRUD operations |
| `simulation/scanner.py` | Repo file discovery → LLM context building → product profile generation |
| `simulation/scripts/run_simulation.py` | OASIS simulation orchestration |
| `simulation/scripts/generate_scorecard.py` | Post grading (A-F), sentiment analysis, engagement metrics |
| `simulation/config/simulation_config.py` | 8 archetype definitions, time/activity configs |
| `simulation/profiles/r_saas_community.json` | Pre-built 18 personas for r/SaaS |
| `simulation/static/index.html` | Single-file SPA (89KB, vanilla JS, dark theme) |

## Important Patterns

- **npm `files` field uses negation patterns** (`!simulation/.venv`, etc.) to exclude dev artifacts from the published package.
- **Python imports use lazy `__import__()`** in cli.py to avoid loading heavy deps (openai, praw) until needed.
- **Venv always lives at `<user-project>/.post-pilot/.venv`** — never inside the bundled package directory. The `simulation/.venv` in dev is for local development only and is excluded from npm.
- **Temp files during simulation** (`run_profiles.json`, `run_post.txt`) are written to the user's `.post-pilot/` directory, not the bundled package dir.
- **`scripts/__init__.py` must exist** — `server.py` imports `scripts.analyze_and_rewrite`, `scripts.generate_html`, etc. as package imports.
- **Simulation runner subprocess** uses `cwd=BASE_DIR` (the simulation dir) and communicates via stdout line protocol.

## Database Schema

8 tables in `.post-pilot/post-pilot.db`: `product` (single row), `community`, `community_profile`, `run`, `run_agent`, `run_comment`, `run_interview`, `run_scorecard`. Full DDL is in `db.py:SCHEMA_SQL`.
