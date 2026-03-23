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
| scraped_at | DATETIME | | when Reddit API was last hit (NULL for seeded/legacy communities) |
| raw_data | TEXT | | JSON blob — raw Reddit API response (top posts, comments, user patterns) |

### `community_profile`

An LLM-generated persona belonging to a community.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | |
| community_id | INTEGER | FK → community NOT NULL | |
| username | TEXT | NOT NULL | generated username (must contain archetype prefix) |
| archetype | TEXT | NOT NULL | e.g., "skeptical_pm", "indie_hacker" |
| persona | TEXT | NOT NULL | behavioral description (200+ chars) |
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
| profile_id | INTEGER | FK → community_profile | NULL if using legacy profiles |
| username | TEXT | NOT NULL | agent username for this run |
| archetype | TEXT | NOT NULL | |
| persona | TEXT | NOT NULL | behavioral description |
| demographics | TEXT | | JSON blob |
| oasis_user_id | INTEGER | | ID in OASIS's internal agent graph |
| engaged | BOOLEAN | NOT NULL DEFAULT 0 | was this agent activated during simulation rounds? |

`run_agent` denormalizes profile data intentionally — profiles can be regenerated, but a run's agents should be immutable history.

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
8. Server streams progress via WebSocket (unchanged)
9. `run_interviews()` writes interview responses directly to `run_interview` table
10. Update `run.status` = 'running'

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

## Scope: Community Selection

This spec establishes the schema for multi-community support but v1 only uses the seeded "r/SaaS" default community. `POST /api/simulate` does not accept a `community_id` parameter yet — it always uses the default. Community management UI and Reddit API integration for generating new communities are deferred to the subreddit persona generation spec.

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
2. Import `r_saas_community.json` as the default "r/SaaS" community + profiles
3. Ready to accept simulations

If the DB already exists, no migration needed (schema is stable from v1).
