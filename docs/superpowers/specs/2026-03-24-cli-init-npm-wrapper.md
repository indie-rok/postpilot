# CLI Init & npm Wrapper

## Overview

Package Post Pilot as an npm-distributed CLI tool (`npx post-pilot`) that wraps the Python backend. Users run `npx post-pilot init` to configure credentials, scan their repo, and build a product profile — then `npx post-pilot serve` to launch the web UI.

## Distribution Model

**npm package** (`post-pilot`) that manages a Python virtual environment under the hood.

Users never interact with Python directly:
```
npx post-pilot init
npx post-pilot serve
```

### npm Wrapper Responsibilities

1. **Find Python** — locate `python3` on PATH, verify version >= 3.11
2. **Create venv** — `python3 -m venv .post-pilot/.venv` (on first run)
3. **Install Python deps** — `.post-pilot/.venv/bin/pip install <npm-package-dir>/python/` (local install from bundled source)
4. **Forward commands** — `npx post-pilot init` → `.post-pilot/.venv/bin/python -m post_pilot init`
5. **Error handling** — clear messages when Python is missing, wrong version, or pip fails

### Python Package Structure

The npm package **bundles** the Python source directly (no separate PyPI package). One release process, one version. The Python package is installed from the local path via `pip install ./python/` during venv setup:
- `post_pilot/` — Python package root
  - `__main__.py` — CLI entry point (`python -m post_pilot`)
  - `cli.py` — Command router (init, configure, learn, serve)
  - `server.py` — FastAPI app (existing, moved from `simulation/`)
  - `db.py` — Database layer (existing, moved from `simulation/`)
  - `scripts/` — Simulation scripts (existing)
  - `static/` — Web UI assets (existing)
  - `config/` — Configuration (existing)

## Commands

### `npx post-pilot init`

Full setup wizard. Runs all steps in sequence. Re-running overwrites everything.

**Steps:**

#### Step 1/3: LLM Configuration
- Prompt for: API Key, Base URL (default: `https://openrouter.ai/api/v1`), Model (default: `gpt-4o-mini`)
- Validate: send a trivial prompt and check for a 200 response (no full generation needed)
- On failure: show error, let user retry or skip validation
- Held in memory until finalization

#### Step 2/3: Reddit API (optional)
- Ask: "Configure Reddit API? Needed for generating community personas from real subreddits. You can skip this and use pre-built communities. [y/N]"
- If yes: prompt for Client ID, Client Secret
- Validate with a test subreddit fetch (`reddit.subreddit("test")`)
- On failure: show error, let user retry or skip
- If skipped: no Reddit vars written, communities rely on pre-built defaults
- Held in memory until finalization

#### Step 3/3: Product Discovery (Deep Scan)
- Scan current directory for project files:
  - `README.md` / `README.rst` — primary product description
  - `package.json` / `pyproject.toml` / `Cargo.toml` / `go.mod` — name, description, dependencies
  - `docs/` — first 3-5 files for additional context
  - File tree structure (top 2 levels) — gives LLM a sense of project scope
  - Source entry points — imports/structure only (not full source code)
- **Scan exclusions** (always skip): `node_modules/`, `.git/`, `dist/`, `build/`, `.next/`, `__pycache__/`, `.venv/`, `vendor/`, `.post-pilot/`, binary files, files > 50KB
- Truncate individual files at ~4KB, total context at ~16KB
- Send to LLM with a structured prompt requesting exactly 4 fields (no more):
  - **Name** — product name (auto-detected)
  - **Problem** — what problem does it solve? One condensed paragraph, no fluff.
  - **Features** — key features, condensed bullet points (3-6 items max)
  - **Who is this for?** — target audience in one sentence
- LLM prompt must explicitly instruct: "Be extremely concise. No marketing language. No filler. Write like a developer explaining their own product to a friend."
- Estimated: 1 LLM call
- Display generated profile summary in terminal (read-only, no edit prompt)
- Full review and editing happens on the web Review screen (see Web UI Changes)

#### Finalization
After all steps, in this order:
1. Create `.post-pilot/` directory
2. Initialize `.post-pilot/post-pilot.db` (create all tables)
3. Write credentials to `.post-pilot/.env`
4. Save product profile to `product` table (DB now exists)
5. Store scanned file content in `product.raw_context` (concatenated scan input, truncated to 16KB)
6. Seed default community (r/SaaS with pre-built personas)
7. Add `.post-pilot/` to `.gitignore` (if `.gitignore` exists, append; if not, create)
8. Print summary:
```
  ✓ Credentials saved to .post-pilot/.env
  ✓ Product profile saved to database
  ✓ Database initialized at .post-pilot/post-pilot.db
  ✓ Default community (r/SaaS) seeded
  ✓ Added .post-pilot/ to .gitignore

  Next: npx post-pilot serve
  Your product profile will be shown for review on first launch.
```

### `npx post-pilot configure`

Runs only Steps 1-2 of the init wizard (LLM + Reddit credentials). Overwrites existing `.post-pilot/.env`.

Use case: changing API keys or switching LLM providers.

### `npx post-pilot learn`

Runs only Step 3 of the init wizard (repo scan). Requires `.post-pilot/.env` to exist with LLM credentials and `.post-pilot/post-pilot.db` to exist.

Use case: re-scanning after major product changes.

**Prerequisite checks:**
- If `.post-pilot/.env` missing or has no `LLM_API_KEY`: prints "No LLM credentials found. Run `npx post-pilot configure` first."
- If `.post-pilot/post-pilot.db` missing: prints "No database found. Run `npx post-pilot init` first."

Overwrites existing product profile in DB. Resets `product.onboarded` to 0 so the web Review screen is shown again.

### `npx post-pilot serve`

Starts the FastAPI web server on port 8000 (or `--port N`).

**Prerequisite check:** Verifies `.post-pilot/post-pilot.db` exists and has a product row.
- If missing: prints "No configuration found. Run `npx post-pilot init` first." and exits with code 1.
- If present: launches `uvicorn post_pilot.server:app --host 0.0.0.0 --port 8000`

## Data Storage

### `.post-pilot/.env` — credentials only

```env
# Post Pilot — LLM Configuration
LLM_API_KEY=sk-...
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=gpt-4o-mini

# Post Pilot — Reddit API (optional)
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
```

Lives inside `.post-pilot/` — no collision with the user's app `.env`. Automatically gitignored because `.post-pilot/` is in `.gitignore`. Developer-editable.

### `.post-pilot/post-pilot.db` — everything else

SQLite database containing:

| Table | Contents |
|---|---|
| `product` | Name, problem, features, audience, raw_context, onboarded. Single-row (id=1). |
| `community` | Subreddit communities |
| `community_profile` | AI personas per community |
| `run` | Simulation runs |
| `run_agent` | Agents per run |
| `run_comment` | Generated comments |
| `run_interview` | Post-simulation interviews |
| `run_scorecard` | Grades and scores |

### Schema Changes (from current)

**`product` table — modifications:**
- Remove: `llm_model`, `llm_base_url`, `llm_api_key` (moved to `.env`)
- Remove: `tagline`, `description`, `pricing` (unnecessary bloat)
- Rename: `target_audience` → `audience` (maps to "Who is this for?")
- Add: `problem TEXT` — what problem does it solve (one condensed paragraph)
- Add: `raw_context TEXT` — full scanned content for LLM reuse
- Add: `onboarded INTEGER DEFAULT 0` — set to 1 after user confirms Review screen in web UI
- Keep: `name`, `features`, `batch_size`, timestamps

**Final `product` columns:** `id`, `name`, `problem`, `features`, `audience`, `raw_context`, `onboarded`, `batch_size`, `created_at`, `updated_at`

**`community` table — no changes.**

**Reddit credentials** — read from `.env` only (currently already the case). Remove from product table if they were added.

### Path Resolution (authoritative rule)

All paths resolve relative to the **user's working directory** (where they ran `npx post-pilot init`):

| Path | Resolved from |
|---|---|
| `.post-pilot/.env` | `process.cwd()` (Node) / `os.getcwd()` (Python) |
| `.post-pilot/post-pilot.db` | `process.cwd()` / `os.getcwd()` |
| `.post-pilot/.venv/` | `process.cwd()` / `os.getcwd()` |

Everything lives under `.post-pilot/`. The npm wrapper passes `cwd` to all Python subprocess calls. Python resolves `DB_PATH` as `Path.cwd() / ".post-pilot" / "post-pilot.db"`. The `dotenv` loader reads `Path.cwd() / ".post-pilot" / ".env"`.

**No paths are relative to the installed package directory.** The package directory contains only source code and bundled assets (pre-built personas, static files).

### Migration from Current Layout

Current layout → new layout:
```
simulation/
  .env                    → .post-pilot/.env (credentials only)
  reddit-sim.db           → .post-pilot/post-pilot.db
  server.py               → post_pilot/server.py (inside npm package)
  db.py                   → post_pilot/db.py (inside npm package)
  scripts/                → post_pilot/scripts/ (inside npm package)
  static/                 → post_pilot/static/ (inside npm package)
```

Key changes: `.env` moves from `simulation/.env` to `.post-pilot/.env`. DB moves from `simulation/reddit-sim.db` to `.post-pilot/post-pilot.db`. All code that calls `load_dotenv()` must resolve from `cwd / ".post-pilot" / ".env"`, not from the package directory.

## Web UI Changes

### Setup View → Review View (one-time)

The old Setup view (credential collection + company.md display) is removed. In its place, a **one-time Review screen** is shown on the first `serve` after `init`.

**Purpose:** Let the user verify and edit the LLM-generated product profile in a proper web form before running any simulations.

**When it appears:**
- `product.onboarded` is `false` (or NULL) → show Review screen
- `product.onboarded` is `true` → skip to Dashboard

**Review screen contents:**
- Post Pilot wordmark + "Here's what we learned about your product. Make any edits before your first simulation."
- Editable form fields: Name, Problem, Features, Who is this for?
- LLM credentials displayed as **read-only** summary (model name + base URL, no key shown) with note: "Edit in `.post-pilot/.env` or run `npx post-pilot configure`"
- "Looks good →" button: sets `product.onboarded = 1`, redirects to Dashboard

**After confirmation:** Never shown again. User edits product info via Settings panel on Dashboard.

**Edge case — `serve` without `init`:** Product row won't exist in DB. Server exits with: "No configuration found. Run `npx post-pilot init` first." The Review screen is never reached without a valid product row.

### Settings Panel — credentials become read-only

The Settings panel shows:

**Product (editable):**
- Name
- Problem
- Features
- Who is this for?

**LLM Configuration (read-only):**
- Model name + Base URL displayed as text (no API key shown)
- Note: "Edit in `.post-pilot/.env` or run `npx post-pilot configure`"

Reason: credentials live in `.post-pilot/.env`, not the DB. The web UI shouldn't write to `.env`.

### Dashboard — default view after onboarding

After the one-time Review screen is confirmed, `serve` always opens to Dashboard.

## npm Package Structure

```
post-pilot/                     (npm package root)
  package.json
  bin/
    post-pilot.js               CLI entry point (Node.js)
  python/
    post_pilot/                 Python package (bundled)
      __init__.py
      __main__.py
      cli.py
      server.py
      db.py
      scripts/
      static/
      config/
      profiles/                 Pre-built community personas
    requirements.txt
    pyproject.toml
```

### `bin/post-pilot.js` — npm CLI entry point

```
#!/usr/bin/env node

1. Parse command: init | configure | learn | serve
2. Check Python 3.11+ available on PATH
3. Ensure venv exists at .post-pilot/.venv (create if not)
4. Ensure Python deps installed (pip install if not)
5. Forward to: .post-pilot/.venv/bin/python -m post_pilot <command> <args>
6. Stream stdout/stderr to terminal
```

### Error Messages

| Condition | Message |
|---|---|
| Python not found | "Python 3.11+ is required. Install from https://python.org" |
| Python version < 3.11 | "Python 3.11+ required, found 3.X. Please upgrade." |
| pip install fails | "Failed to install dependencies. Check your internet connection." |
| `serve` without init | "No configuration found. Run `npx post-pilot init` first." |
| `learn` without .env | "No LLM credentials found. Run `npx post-pilot configure` first." |
| LLM validation fails | "Could not connect to LLM. Check your API key and base URL." |
| Reddit validation fails | "Could not connect to Reddit API. Check your credentials." |

## Pre-built Communities

The package ships with at least one pre-built community so users can simulate immediately after init, even without Reddit API credentials.

**Shipped community: r/SaaS**
- Pre-generated personas (JSON) bundled in `profiles/`
- Seeded into DB during init finalization
- Users can generate more communities via the web UI (if Reddit API is configured)

## Interactive CLI Library

Use Python's built-in `input()` + `getpass.getpass()` for credential prompts. No external dependency (like `rich` or `questionary`) needed for the MVP.

Formatting uses simple print statements with Unicode box-drawing characters for the profile display.

## Out of Scope

- **Multiple projects** — one project per directory, single-row product table
- **Team/sharing features** — single-user tool
- **Cloud storage** — everything local (SQLite + .env)
- **Auto-updates** — user runs `npm update post-pilot` manually
- **Windows support** — best-effort, not a priority for v1
- **GUI installer** — CLI only
