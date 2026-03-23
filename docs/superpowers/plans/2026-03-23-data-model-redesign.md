# Data Model Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate all app data into a single SQLite DB with run history, replacing the current mix of JSON files, text files, and per-run OASIS databases.

**Architecture:** New `simulation/db.py` module owns the schema and all DB access. **Server** owns pre-simulation setup (creating run + run_agent rows, writing temp files for OASIS). **Subprocess** (`run_simulation.py`) receives `run_id` + `app_db_path`, maps OASIS agent IDs, runs sim, extracts results into app DB, writes interviews to DB, deletes OASIS temp DB. All endpoints read/write from app DB.

**Tech Stack:** Python 3.11, SQLite3, FastAPI, OASIS (camel-ai)

**Spec:** `docs/superpowers/specs/2026-03-23-data-model-redesign.md`

**Scope:** This is **Plan 1 of 2**. Covers DB foundation, simulation refactor, run history. Does NOT cover community management API (create/approve/refresh/edit communities) or Reddit API integration — those are Plan 2.

---

## Ownership Model

| Responsibility | Owner |
|---|---|
| Create `run` + `run_agent` rows | `server.py` (before spawning subprocess) |
| Write temp profile JSON + post file for OASIS | `server.py` |
| Map `oasis_user_id` after agent graph creation | `run_simulation.py` (persists to DB) |
| Run simulation rounds | `run_simulation.py` |
| Extract OASIS results into app DB | `run_simulation.py` |
| Write interviews to `run_interview` | `run_simulation.py` |
| Delete OASIS temp DB | `run_simulation.py` |
| Update `run.status` | `run_simulation.py` (running → complete/failed) |

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `simulation/db.py` | Create | Schema, init, seed, ALL query/mutation helpers |
| `simulation/tests/test_db.py` | Create | Tests for DB module |
| `simulation/scripts/run_simulation.py` | Modify | Receives run_id, maps oasis_user_id, extracts results, writes interviews |
| `simulation/scripts/generate_scorecard.py` | Modify | Read/write from app DB instead of OASIS DB + JSON files |
| `simulation/scripts/generate_html.py` | Modify | Read from app DB instead of OASIS DB + profiles JSON |
| `simulation/server.py` | Modify | Creates run/agents, uses app DB for all endpoints, run history API |
| `simulation/static/index.html` | Modify | Run history sidebar |

---

### Task 1: Create DB schema module with init and seed

**Files:**
- Create: `simulation/db.py`
- Create: `simulation/tests/test_db.py`

- [ ] **Step 1: Write failing tests for DB init**

Create `simulation/tests/test_db.py`:

```python
import json
import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db import init_db, get_connection, seed_default_community


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


def test_init_db_creates_tables(db_path):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {r[0] for r in cur.fetchall()}
    conn.close()
    expected = {
        "community", "community_profile", "run", "run_agent",
        "run_comment", "run_interview", "run_scorecard",
    }
    assert expected.issubset(tables)


def test_init_db_idempotent(db_path):
    init_db(db_path)
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM community")
    assert cur.fetchone()[0] == 0
    conn.close()


def test_get_connection(db_path):
    init_db(db_path)
    conn = get_connection(db_path)
    assert conn is not None
    conn.close()


def test_seed_default_community(db_path):
    init_db(db_path)
    profiles_path = os.path.join(
        os.path.dirname(__file__), "..", "profiles", "r_saas_community.json"
    )
    seed_default_community(db_path, profiles_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT subreddit, status FROM community WHERE id = 1")
    row = cur.fetchone()
    assert row[0] == "r/SaaS"
    assert row[1] == "active"

    cur.execute("SELECT COUNT(*) FROM community_profile WHERE community_id = 1")
    count = cur.fetchone()[0]
    assert count == 18

    cur.execute("SELECT username, realname, archetype, bio, persona FROM community_profile LIMIT 1")
    row = cur.fetchone()
    assert row[0] is not None
    assert row[1] is not None
    assert row[2] is not None
    assert row[3] is not None
    assert len(row[4]) > 100

    conn.close()


def test_seed_idempotent(db_path):
    init_db(db_path)
    profiles_path = os.path.join(
        os.path.dirname(__file__), "..", "profiles", "r_saas_community.json"
    )
    seed_default_community(db_path, profiles_path)
    seed_default_community(db_path, profiles_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM community")
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT COUNT(*) FROM community_profile")
    assert cur.fetchone()[0] == 18
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest simulation/tests/test_db.py -v`
Expected: FAIL — `db` module does not exist.

- [ ] **Step 3: Implement `simulation/db.py`**

Create `simulation/db.py` with:

1. `SCHEMA_SQL` — a multi-statement string with all 7 CREATE TABLE IF NOT EXISTS statements matching the spec exactly (community, community_profile, run, run_agent, run_comment, run_interview, run_scorecard). Use the exact column names, types, and constraints from the spec.

2. `init_db(db_path: str) -> None` — connects, executes `SCHEMA_SQL` with `executescript()`, closes.

3. `get_connection(db_path: str) -> sqlite3.Connection` — returns a connection with `row_factory = sqlite3.Row` and `execute("PRAGMA foreign_keys = ON")`.

4. `seed_default_community(db_path: str, profiles_path: str) -> None`:
   - Check if community with `subreddit = 'r/SaaS'` already exists → return if so
   - Insert community row: `subreddit='r/SaaS'`, `status='active'`, `scraped_at=NULL`
   - Read `profiles_path` JSON, for each profile insert a `community_profile` row:
     - `username` from profile `username`
     - `realname` from profile `realname`
     - `archetype` — derive from username using prefix matching (same logic as existing `_archetype_for`)
     - `bio` from profile `bio`
     - `persona` from profile `persona`
     - `demographics` — JSON blob with `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`
     - `generated_at` — current UTC timestamp

Key schema details from the spec:
- `community.status` TEXT NOT NULL DEFAULT 'draft'
- `run_agent.profile_id` INTEGER (NOT a foreign key — just informational)
- `run.post_likes` and `run.post_dislikes` INTEGER NOT NULL DEFAULT 0
- `run_scorecard.run_id` has UNIQUE constraint

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest simulation/tests/test_db.py -v`
Expected: All 5 pass.

- [ ] **Step 5: Commit**

```bash
git add simulation/db.py simulation/tests/test_db.py
git commit -m "feat: add DB schema module with init and seed"
```

---

### Task 2: DB helpers for run lifecycle + queries

**Files:**
- Modify: `simulation/db.py` — add all CRUD/query helpers
- Create: `simulation/tests/test_run_creation.py`

- [ ] **Step 1: Write failing tests**

Create `simulation/tests/test_run_creation.py` testing:
- `create_run(db_path, tag, community_id, post_content, agent_count, total_hours, llm_model)` → returns `run_id`, row exists with `status='pending'`
- `create_run_agents(db_path, run_id, profiles)` → creates `run_agent` rows with correct fields, returns list of `(run_agent_id, username)` tuples
- `update_run_status(db_path, run_id, status)` → updates status column
- `update_oasis_user_id(db_path, run_agent_id, oasis_user_id)` → persists oasis_user_id
- `get_agent_mapping(db_path, run_id)` → returns dict mapping `username → run_agent_id`
- `select_profiles_for_community(db_path, community_id, count)` → returns list of profile dicts, uses `archetype` column for diversity (NOT username-prefix)
- `get_results_for_run(db_path, run_id)` → returns dict with post, comments, profiles, stats (same shape as current `generate_html.extract_data()`)
- `list_runs(db_path)` → returns list of run summaries
- `delete_run(db_path, run_id)` → cascading delete of all associated data

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement all helpers in `simulation/db.py`**

Key functions:
- `create_run(...)` — INSERT into run, return `lastrowid`
- `create_run_agents(db_path, run_id, profiles: list[dict])` — INSERT into run_agent with all denormalized fields (username, realname, archetype, bio, persona, demographics, profile_id). Return list of `(run_agent_id, username)` tuples.
- `update_run_status(db_path, run_id, status, completed_at=None)` — UPDATE run
- `update_oasis_user_id(db_path, run_agent_id, oasis_user_id)` — UPDATE run_agent SET oasis_user_id
- `get_agent_mapping(db_path, run_id)` — SELECT username, id FROM run_agent WHERE run_id, returns `dict[str, int]`
- `select_profiles_for_community(db_path, community_id, count)` — diverse selection using the `archetype` column (NOT username prefix). Groups profiles by archetype, round-robin selects, ensures at least one skeptic and one founder. Returns list of dicts.
- `get_results_for_run(db_path, run_id)` — query run + run_comment + run_agent to build same JSON shape as current `extract_data()` output
- `list_runs(db_path)` — SELECT with comment count subquery, ORDER BY created_at DESC
- `delete_run(db_path, run_id)` — DELETE from run_scorecard, run_interview, run_comment, run_agent, run WHERE id = run_id

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add simulation/db.py simulation/tests/test_run_creation.py
git commit -m "feat: add run lifecycle and query DB helpers"
```

---

### Task 3: OASIS extraction helpers + refactor run_simulation.py

**Files:**
- Modify: `simulation/db.py` — add extraction + interview helpers
- Modify: `simulation/scripts/run_simulation.py` — receives run_id, maps oasis IDs, extracts results, writes interviews to DB
- Create: `simulation/tests/test_extraction.py`

- [ ] **Step 1: Write failing tests for extraction**

Create `simulation/tests/test_extraction.py` testing:
- `extract_oasis_results(app_db_path, oasis_db_path, run_id, agent_mapping)`:
  - Given a pre-populated OASIS DB fixture with known comments/likes, verify:
    - `run_comment` rows created with correct content, likes, dislikes, agent_id
    - `run.post_likes` and `run.post_dislikes` populated
    - `run_agent.engaged` updated for agents with non-silent actions
- `insert_interview(db_path, run_id, agent_id, response)` — creates `run_interview` row

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement extraction in `simulation/db.py`**

`extract_oasis_results(app_db_path, oasis_db_path, run_id, agent_mapping: dict[int, int])`:
- `agent_mapping` maps OASIS user_id → run_agent.id
- From OASIS DB:
  - `comment` rows → INSERT into `run_comment` (map user_id via agent_mapping)
  - `comment_like` / `comment_dislike` counts per comment → UPDATE `run_comment.likes/dislikes`
  - `like` / `dislike` counts (post-level) → UPDATE `run.post_likes/post_dislikes`
  - `trace` table → UPDATE `run_agent.engaged = 1` for agents with non-silent actions

`insert_interview(db_path, run_id, agent_id, response)`:
- INSERT into `run_interview`

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Refactor `run_simulation.py`**

The function now receives `run_id` and `app_db_path` as arguments (passed by server via subprocess env vars `RUN_ID` and `APP_DB_PATH`).

**New args:** Add `--run-id` and `--app-db` CLI args. Read from env vars as fallback.

**After OASIS agent graph is created:**
- Iterate `env.agent_graph.get_agents()`, match each agent's username to a `run_agent` row
- Call `update_oasis_user_id(app_db_path, run_agent_id, oasis_agent_id)` for each
- Build `agent_mapping: dict[int, int]` (oasis_user_id → run_agent_id)

**After env.step(seed_action):**
- Call `update_run_status(app_db_path, run_id, 'running')`

**After simulation rounds complete, before interviews:**
- Call `extract_oasis_results(app_db_path, oasis_db_path, run_id, agent_mapping)`

**During `run_interviews()`:**
- After each interview, call `insert_interview(app_db_path, run_id, agent_id, response)` instead of appending to a list
- Remove JSON interview file writing

**After interviews:**
- Delete OASIS temp DB file
- Call `update_run_status(app_db_path, run_id, 'complete', completed_at=now)`

**Remove:** `load_profiles()` function (profiles come from temp file written by server). Remove `load_post_content()` (post comes from temp file written by server).

- [ ] **Step 6: Run all tests**

Run: `python -m pytest simulation/tests/ -v`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add simulation/db.py simulation/scripts/run_simulation.py simulation/tests/test_extraction.py
git commit -m "feat: extract OASIS results into app DB, write interviews to DB"
```

---

### Task 4: Archetype migration — remove username-prefix derivation

**Files:**
- Modify: `simulation/scripts/run_simulation.py` — replace `get_archetype()` with DB archetype
- Modify: `simulation/scripts/generate_scorecard.py` — remove `_archetype_for()` / `ARCHETYPE_PREFIXES`
- Modify: `simulation/scripts/generate_html.py` — remove `archetype_prefixes` dict

- [ ] **Step 1: Refactor `run_simulation.py`**

- Remove `get_archetype(username)` function
- In `get_active_agents_for_hour()`: archetype must come from the agent's profile data (loaded from temp profiles JSON which now includes an `archetype` field), not from username prefix
- Update `run_interviews()`: archetype comes from the run_agent record, not `get_archetype(username)`
- The temp profiles JSON (written by server before spawning subprocess) must include the `archetype` field

- [ ] **Step 2: Refactor `generate_scorecard.py`**

- Remove `ARCHETYPE_PREFIXES` dict and `_archetype_for()` function
- Archetype now comes from the `run_comment`/`run_agent` join (DB column), not username parsing

- [ ] **Step 3: Refactor `generate_html.py`**

- Remove `archetype_prefixes` dict and the username-prefix loop
- Archetype comes from the `run_agent` rows in the DB query results

- [ ] **Step 4: Run all tests**

Run: `python -m pytest simulation/tests/ -v`
Expected: All pass. Update any tests that relied on `get_archetype()` or `_archetype_for()`.

- [ ] **Step 5: Commit**

```bash
git add simulation/scripts/run_simulation.py simulation/scripts/generate_scorecard.py simulation/scripts/generate_html.py
git commit -m "refactor: use DB archetype column as source of truth, remove username-prefix derivation"
```

---

### Task 5: Refactor generate_scorecard.py to use app DB

**Files:**
- Modify: `simulation/scripts/generate_scorecard.py`
- Modify: `simulation/db.py` — add scorecard query helpers

- [ ] **Step 1: Add DB query helpers**

In `db.py`, add:
- `get_comments_for_run(db_path, run_id)` — returns list of dicts with comment content, author username, archetype, likes, dislikes
- `get_interviews_for_run(db_path, run_id)` — returns list of dicts with interview response, username, archetype
- `get_engagement_metrics_from_db(db_path, run_id)` — returns the same shape as current `query_engagement_metrics()` but from app DB tables
- `get_archetype_participation_from_db(db_path, run_id)` — same shape as current `query_archetype_participation()` but from app DB
- `save_scorecard(db_path, run_id, score, grade, summary, data_json)` — INSERT into run_scorecard
- `update_comment_sentiment(db_path, comment_id, sentiment)` — UPDATE run_comment SET sentiment
- `update_interview_classification(db_path, interview_id, clarity, would_click, would_signup)` — UPDATE run_interview

- [ ] **Step 2: Refactor `generate_scorecard.py`**

- Replace `query_engagement_metrics(oasis_db_path)` with `get_engagement_metrics_from_db(app_db_path, run_id)`
- Replace `query_archetype_participation(oasis_db_path, profiles_path)` with `get_archetype_participation_from_db(app_db_path, run_id)`
- Replace reading interviews from JSON file with `get_interviews_for_run(app_db_path, run_id)`
- Replace reading comments from OASIS DB with `get_comments_for_run(app_db_path, run_id)`
- After classification: call `update_comment_sentiment()` and `update_interview_classification()` to persist results
- After scorecard built: call `save_scorecard()` to persist
- Remove `_archetype_for()` / `ARCHETYPE_PREFIXES` username-prefix logic — archetype now comes from the DB column directly
- Update function signatures: `generate_scorecard(db_path, run_id, batch_size=0)` instead of `(db_path, profiles_path, batch_size=0)`

- [ ] **Step 3: Update existing scorecard tests**

Modify `simulation/tests/test_scorecard.py`:
- Tests that use OASIS DB fixtures need updating to use app DB fixtures
- Create test helper that sets up an app DB with known run/agent/comment/interview data

- [ ] **Step 4: Run all tests**

Run: `python -m pytest simulation/tests/ -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add simulation/scripts/generate_scorecard.py simulation/db.py simulation/tests/test_scorecard.py
git commit -m "refactor: scorecard reads from app DB instead of OASIS DB"
```

---

### Task 6: Refactor generate_html.py to use app DB (depends on Task 2 helpers)

**Files:**
- Modify: `simulation/scripts/generate_html.py`

- [ ] **Step 1: Refactor `extract_data()`**

Change signature from `extract_data(db_path, profiles_path)` to `extract_data(app_db_path, run_id_or_tag)`.

- Read post content from `run.post_content`, likes from `run.post_likes/post_dislikes`
- Read comments from `run_comment` joined with `run_agent` (gets author, archetype, bio)
- Build profile_map from `run_agent` rows instead of reading JSON file
- Remove `archetype_prefixes` dict and username-prefix derivation
- Return same JSON shape so the HTML template still works

- [ ] **Step 2: Update server.py call sites**

Update `get_thread()` and `get_results()` in server.py to call the new signature.

- [ ] **Step 3: Run tests**

Run: `python -m pytest simulation/tests/ -v`

- [ ] **Step 4: Commit**

```bash
git add simulation/scripts/generate_html.py simulation/server.py
git commit -m "refactor: thread view reads from app DB"
```

---

### Task 7: Refactor server.py to use app DB (depends on Tasks 2, 3, 5, 6)

**Files:**
- Modify: `simulation/server.py`
- Modify: `simulation/db.py` (if additional helpers needed)

- [ ] **Step 1: Add DB initialization on startup**

Add a FastAPI `lifespan` or `on_event("startup")` handler that calls:
```python
from db import init_db, seed_default_community
APP_DB = BASE_DIR / "reddit-sim.db"
init_db(str(APP_DB))
seed_default_community(str(APP_DB), str(ALL_PROFILES_PATH))
```

- [ ] **Step 2: Refactor `/api/simulate` endpoint**

Server now owns pre-simulation setup:
- Call `select_profiles_for_community(app_db_path, community_id, agent_count)` to get profiles
- Call `create_run()` to get `run_id`
- Call `create_run_agents()` to create agent rows
- Write temp profile JSON + post file for OASIS (from DB data — include `archetype` field in JSON)
- Pass `run_id` and `app_db_path` to subprocess via `RUN_ID` and `APP_DB_PATH` env vars
- Remove `cleanup_previous_run()`, `RUN_POST_PATH`, `RUN_PROFILES_PATH`
- Update `RUNNER_WRAPPER` to pass `--run-id` and `--app-db` to run_simulation.py

- [ ] **Step 3: Refactor `/api/results/{tag}` endpoint**

- Use `get_results_for_run(app_db_path, run_id)` from `db.py` instead of `extract_sim_data(oasis_db_path, profiles_path)`
- Look up run_id from tag via DB query

- [ ] **Step 4: Refactor `/api/scorecard/{tag}` endpoint**

- Check `run_scorecard` table for cached result first
- If not cached, call scorecard generation (which now reads from app DB via Task 5 refactoring)
- Result is stored in `run_scorecard` table by scorecard module

- [ ] **Step 5: Refactor `/api/rewrite/{tag}` endpoint**

- Read scorecard from `run_scorecard` table
- Read original post from `run.post_content`

- [ ] **Step 6: Add run history endpoints**

`GET /api/runs` — calls `list_runs(app_db_path)` from db.py
`DELETE /api/runs/{tag}` — calls `delete_run(app_db_path, run_id)` from db.py

- [ ] **Step 7: Remove unused imports and cast wrappers**

Remove `analyze_module`, `generate_html_module` imports and the associated cast wrappers if no longer used. Remove `resolve_profiles_for_tag()`, `select_diverse_profiles()` (replaced by DB version).

- [ ] **Step 8: Verify server starts**

```bash
cd simulation && python -c "from server import app; print('OK')"
```

- [ ] **Step 9: Commit**

```bash
git add simulation/server.py simulation/db.py
git commit -m "refactor: server endpoints use app DB, add run history API"
```

---

### Task 8: Run history UI in sidebar

**Files:**
- Modify: `simulation/static/index.html`

- [ ] **Step 1: Add run history list to sidebar**

After the launch button and progress panel, add a run history section:
- Header: "Run History"
- Fetch `GET /api/runs` on page load
- Render each run as a clickable item showing: tag, status, agent count, timestamp, comment count
- Clicking a run loads its results into the right panel
- Active run is highlighted
- Each run has a delete button (calls `DELETE /api/runs/{tag}`)

- [ ] **Step 2: Wire click handlers**

When a run is clicked:
- Call `GET /api/results/{tag}` to load thread data
- Call existing scorecard/analysis load if available
- Update active state

- [ ] **Step 3: Auto-refresh after simulation completes**

After `simulationDone()`, re-fetch the run list to show the new run.

- [ ] **Step 4: Verify page loads**

```bash
cd simulation && python -c "from server import app; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add simulation/static/index.html
git commit -m "feat: add run history sidebar"
```

---

### Task 9: Cleanup — remove flat file dependencies

**Files:**
- Modify: `simulation/server.py`
- Modify: `simulation/scripts/run_simulation.py`

- [ ] **Step 1: Remove flat file code from server.py**

- Remove `RUN_PROFILES_PATH`, `RUN_POST_PATH` constants
- Remove `cleanup_previous_run()` function
- Remove `resolve_profiles_for_tag()` function
- Remove cast wrappers for `fetch_comments`, `fetch_original_post` if no longer used
- Remove `analyze_module` imports if analyze endpoint is removed/simplified

- [ ] **Step 2: Remove flat file code from run_simulation.py**

- Remove JSON interview file writing (interviews go to DB now)
- Remove `load_post_content()` if post comes from DB
- Remove `load_profiles()` if profiles come from DB

- [ ] **Step 3: Run all tests**

Run: `python -m pytest simulation/tests/ -v`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add simulation/server.py simulation/scripts/run_simulation.py
git commit -m "refactor: remove flat file dependencies, all data flows through app DB"
```

---

### Task 10: Manual integration test

- [ ] **Step 1: Start fresh**

Delete any existing `reddit-sim.db` to test init + seed from scratch.

```bash
cd simulation && rm -f reddit-sim.db
```

- [ ] **Step 2: Start the server**

```bash
source .venv/bin/activate && uvicorn server:app --host 0.0.0.0 --port 8000
```

Verify: Server starts, creates `reddit-sim.db`, seeds r/SaaS community with 18 profiles.

- [ ] **Step 3: Run a simulation**

Open `http://localhost:8000`, configure 4 agents / 1 hour, launch. Verify:
1. Simulation completes without errors
2. Progress bar works
3. Thread tab shows post + comments
4. Run appears in sidebar history
5. Scorecard generates correctly

- [ ] **Step 4: Run a second simulation**

Launch another simulation with different post content. Verify:
1. Both runs appear in sidebar
2. Clicking between runs loads different results
3. Old run data is preserved

- [ ] **Step 5: Delete a run**

Click delete on one run. Verify it disappears from sidebar and data is cleaned up.
