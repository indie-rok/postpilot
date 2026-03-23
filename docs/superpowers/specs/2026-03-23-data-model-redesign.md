# Data Model Redesign

## Overview

Consolidate all application data into a single SQLite database (`reddit-sim.db`). Replace the current mix of JSON files, text files, and per-run OASIS databases with a normalized schema that supports run history, reusable community profiles, and a clean separation between OASIS internals and our application data.

## Goals

- Single source of truth for all app data
- Run history preserved — users can browse, compare past simulations
- Communities and personas are reusable across runs
- OASIS writes to a temp DB during simulation; we extract and normalize results into ours after completion
- Foundation for subreddit-based persona generation and OSS packaging

## Current State (being replaced)

| Data | Format | Problem |
|---|---|---|
| Agent profiles | `profiles/r_saas_community.json` | Static, not reusable across communities |
| Run profiles | `profiles/run_profiles.json` | Overwritten each run |
| Post content | `posts/run_post.txt` | Overwritten each run |
| Simulation DB | `results/run.db` (OASIS SQLite) | Overwritten each run, 20+ tables mostly empty |
| Interviews | `results/run_interviews.json` | Overwritten each run |
| Scorecard | `results/run_scorecard.json` | Overwritten each run |
| LLM config | `.env` | Stays as-is (credentials) |

## Database Schema

Single file: `reddit-sim.db` in the project's data directory.

### `community`

A parsed subreddit whose member patterns have been analyzed.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | |
| subreddit | TEXT | UNIQUE NOT NULL | e.g., "r/SaaS" |
| status | TEXT | NOT NULL DEFAULT 'draft' | draft (pending approval) / active (ready for simulation) |
| scraped_at | DATETIME | | when Reddit API was last hit (NULL for seeded/legacy communities) |
| raw_data | TEXT | | JSON blob — raw Reddit API response (top posts, comments, user patterns) |

### `community_profile`

An LLM-generated persona belonging to a community.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | |
| community_id | INTEGER | FK → community NOT NULL | |
| username | TEXT | NOT NULL | generated username (must contain archetype prefix) |
| realname | TEXT | NOT NULL | display name (e.g., "Maya Chen") |
| archetype | TEXT | NOT NULL | e.g., "skeptical_pm", "indie_hacker" |
| bio | TEXT | | short bio used for thread rendering and scorecard archetype descriptions |
| persona | TEXT | NOT NULL | behavioral description (200+ chars) — drives LLM agent behavior |
| demographics | TEXT | | JSON blob — age, gender, mbti, country, profession, interested_topics |
| generated_at | DATETIME | NOT NULL | |

### `run`

A simulation execution — the central entity connecting everything.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | |
| tag | TEXT | UNIQUE NOT NULL | human-readable label, auto-generated if not provided |
| community_id | INTEGER | FK → community | which audience was simulated |
| post_content | TEXT | NOT NULL | full post text as submitted |
| post_source | TEXT | NOT NULL DEFAULT 'manual' | "manual", "readme_generated", "rewrite" |
| agent_count | INTEGER | NOT NULL | |
| total_hours | INTEGER | NOT NULL | |
| llm_model | TEXT | | model used for this run |
| status | TEXT | NOT NULL DEFAULT 'pending' | pending / running / complete / failed |
| post_likes | INTEGER | NOT NULL DEFAULT 0 | post-level likes (from OASIS `like` table) |
| post_dislikes | INTEGER | NOT NULL DEFAULT 0 | post-level dislikes (from OASIS `dislike` table) |
| created_at | DATETIME | NOT NULL | |
| completed_at | DATETIME | | |

### `run_agent`

Which profiles were selected and used in a run.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | |
| run_id | INTEGER | FK → run NOT NULL | |
| profile_id | INTEGER | | source profile ID at time of run (informational only, not an FK — profiles may be deleted on refresh) |
| username | TEXT | NOT NULL | agent username for this run |
| realname | TEXT | NOT NULL | display name |
| archetype | TEXT | NOT NULL | |
| bio | TEXT | | |
| persona | TEXT | NOT NULL | behavioral description |
| demographics | TEXT | | JSON blob |
| oasis_user_id | INTEGER | | ID in OASIS's internal agent graph |
| engaged | BOOLEAN | NOT NULL DEFAULT 0 | was this agent activated during simulation rounds? |

`run_agent` denormalizes profile data intentionally — profiles can be regenerated or deleted on refresh, but a run's agents are immutable history. `profile_id` is stored for traceability but is NOT a foreign key — it won't break if the source profile is deleted.

### Archetype source of truth

The `archetype` column on `community_profile` and `run_agent` is the canonical source of truth. The legacy pattern of deriving archetype from username prefixes (via `get_archetype()` in `run_simulation.py`) must be replaced: all code that needs an agent's archetype should read it from the `archetype` column, not infer it from the username string. Usernames no longer need to contain archetype prefixes — they can be any generated name.

### `run_comment`

Comments extracted from OASIS DB after simulation.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | |
| run_id | INTEGER | FK → run NOT NULL | |
| agent_id | INTEGER | FK → run_agent NOT NULL | |
| content | TEXT | NOT NULL | |
| likes | INTEGER | NOT NULL DEFAULT 0 | |
| dislikes | INTEGER | NOT NULL DEFAULT 0 | |
| created_at | DATETIME | | |
| sentiment | TEXT | | positive / neutral / negative — populated by scorecard classification |

### `run_interview`

Post-simulation interview responses.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | |
| run_id | INTEGER | FK → run NOT NULL | |
| agent_id | INTEGER | FK → run_agent NOT NULL | |
| response | TEXT | NOT NULL | raw interview response |
| clarity | TEXT | | accurate / partial / wrong — populated by scorecard classification |
| would_click | BOOLEAN | | extracted from interview |
| would_signup | BOOLEAN | | extracted from interview |

### `run_scorecard`

Cached scorecard analysis per run.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | |
| run_id | INTEGER | FK → run UNIQUE NOT NULL | one scorecard per run |
| score | REAL | | 0.0–10.0 |
| grade | TEXT | | A+, A, B+, B, C+, C, D, F |
| summary | TEXT | | one-line summary |
| data | TEXT | NOT NULL | JSON blob — full scorecard payload (matrix, funnel, objections, etc.) |
| created_at | DATETIME | NOT NULL | |

## Simulation Flow (revised)

### Before simulation

1. User selects community (or uses existing one)
2. Server selects N profiles from `community_profile` for the chosen community
3. Creates a `run` row (status=pending)
4. Creates `run_agent` rows for selected profiles
5. Writes post content to a temp file (OASIS needs a file path)
6. Writes selected profiles to a temp JSON file (OASIS needs a file path)

### During simulation

7. OASIS writes to a temp SQLite DB (`/tmp/reddit-sim-{run_id}.db` or similar)
8. After OASIS agent graph is created, populate `run_agent.oasis_user_id` by matching usernames between `run_agent` rows and OASIS's agent graph entries. This mapping is needed for interview writes and post-run extraction.
9. Server streams progress via WebSocket (unchanged)
10. Update `run.status` = 'running'
11. `run_interviews()` uses the `oasis_user_id` ↔ `run_agent.id` mapping to write interview responses directly to `run_interview` with the correct `agent_id`

### After simulation

11. Extract from OASIS temp DB:
    - `comment` table → `run_comment` rows (join with `user` table to resolve agent mapping)
    - `comment_like` / `comment_dislike` tables → aggregate counts into `run_comment.likes` / `.dislikes`
    - `like` / `dislike` tables (post-level) → aggregate counts into `run.post_likes` / `.post_dislikes`
    - `trace` table → update `run_agent.engaged` based on which agents had actions
12. Delete OASIS temp DB
13. Update `run.status` = 'complete', `run.completed_at` = now

### Scorecard generation

14. Read comments from `run_comment` (instead of querying OASIS DB)
15. Read interviews from `run_interview` (instead of JSON file)
16. Run LLM classification, write results back:
    - `run_comment.sentiment` updated
    - `run_interview.clarity`, `.would_click`, `.would_signup` updated
    - `run_scorecard` row created with full JSON blob
17. UI reads scorecard from `run_scorecard.data`

## Migration from Current State

For the existing `r_saas_community.json` profiles:

1. On first run, create a `community` row for "r/SaaS" with `raw_data = NULL` (no Reddit API scrape for this legacy community)
2. Import all 18 profiles as `community_profile` rows
3. This becomes the default community until user generates a new one

Existing `results/run.db` data is not migrated — it's a single overwritten run with no history value.

## File Layout (after redesign)

```
reddit-sim.db              ← single app database
/tmp/reddit-sim-{id}.db   ← temp OASIS DB (deleted after each run)
.env                       ← credentials only (LLM key, Reddit API key)
```

No more `profiles/`, `posts/`, `results/` directories with loose files.

## Community Selection Flow

### Community status

`community` has a `status` column:
- `draft` — profiles have been generated but not yet approved by the user
- `active` — profiles are approved and ready for simulation

Only `active` communities appear in the simulation community selector.

### Three scenarios

**1. New community** — user enters a subreddit that doesn't exist in DB:
- Create `community` row with `status = 'draft'`
- Scrape Reddit API (top posts, comments, active user patterns) → store in `community.raw_data`
- LLM generates personas from scraped data → save as `community_profile` rows
- Show generated personas for review — user can edit individual profiles or remove agents
- User clicks "Approve" → `community.status` = `'active'`, community is ready for simulation

**2. Existing active community, no changes needed** — user selects from dropdown:
- Show profile count + "last generated X days ago"
- User can launch simulation immediately
- User can still edit individual profiles at any time (edits save directly)

**3. Existing community, user wants to refresh** — user clicks refresh:
- Set `community.status` = `'draft'`
- Re-scrape Reddit API, update `community.raw_data` and `community.scraped_at`
- Delete existing `community_profile` rows for this community (safe — `run_agent.profile_id` is not an FK, past runs are unaffected)
- LLM generates new personas → save as new `community_profile` rows
- Show for review (same edit flow as scenario 1)
- User approves → `community.status` = `'active'`

### Persona editing

`community_profile` rows are editable templates. Users can:
- Edit any field: username, realname, archetype, bio, persona text, demographics
- Remove profiles from the community

When a simulation launches, selected profiles are **copied** into `run_agent` rows. That snapshot is immutable — editing or deleting community profiles afterward does not affect past runs.

### API endpoints for community management

| Endpoint | Method | Purpose |
|---|---|---|
| `GET /api/communities` | GET | List all communities with profile counts, status, and last-generated dates |
| `POST /api/communities` | POST | Create new community: accepts subreddit name, scrapes Reddit API, generates personas via LLM. Returns community (status=draft) + profiles |
| `POST /api/communities/{id}/approve` | POST | Set community status to active |
| `GET /api/communities/{id}/profiles` | GET | List all profiles for a community |
| `PUT /api/communities/{id}/profiles/{profile_id}` | PUT | Edit a single profile |
| `DELETE /api/communities/{id}/profiles/{profile_id}` | DELETE | Remove a profile from a community |
| `POST /api/communities/{id}/refresh` | POST | Re-scrape + regenerate all profiles, sets status back to draft |

### Simulate endpoint change

`POST /api/simulate` gains a `community_id` parameter. Server validates the community has `status = 'active'` before allowing simulation. If `community_id` is omitted, uses the default seeded "r/SaaS" community.

## What Does NOT Change

- OASIS library internals — we still use `oasis.make()`, `env.step()`, etc.
- LLM configuration — stays in `.env` and UI overrides
- WebSocket progress streaming — still works the same way
- Scorecard generation logic — same LLM classification, just reads/writes DB instead of JSON files
- The web UI rendering — still receives the same JSON payloads from API endpoints

## API Endpoint Changes

| Endpoint | Current | After |
|---|---|---|
| `POST /api/simulate` | Creates flat files, overwrites run.db | Creates `run` + `run_agent` rows, OASIS writes to temp DB, extracts results |
| `GET /api/results/{tag}` | Reads OASIS DB directly | Reads from `run_comment` + `run_agent` tables |
| `POST /api/scorecard/{tag}` | Reads OASIS DB + interviews JSON, caches to JSON | Reads from `run_comment` + `run_interview`, writes to `run_scorecard` |
| `POST /api/rewrite/{tag}` | Reads OASIS DB | Reads from `run_scorecard.data` |
| `GET /api/runs` | Does not exist | NEW — returns list of all runs for sidebar history |
| `DELETE /api/runs/{tag}` | Does not exist | NEW — deletes a run and its associated data |

## DB Initialization

On server startup, if `reddit-sim.db` does not exist:
1. Create all tables with schema above
2. Import `r_saas_community.json` as the default "r/SaaS" community with `status = 'active'` and `scraped_at = NULL` (seeded, not scraped)
3. Import all 18 profiles as `community_profile` rows with `generated_at` set to current timestamp
4. Ready to accept simulations

If the DB already exists, no migration needed (schema is stable from v1).
