# UX Redesign: Phased Views

## Overview

Redesign the single-page simulation UI into a multi-view application with URL routing, a product onboarding step, a community-centric dashboard, and dedicated screens for adding communities and running simulations.

## Views

### 1. Setup (`/setup`)

First-time experience. Shown when no product data exists in the DB.

**Input**: reads `company.md` from the working directory if it exists, otherwise shows an empty form.

**Form fields**:
- Company/product name
- One-liner description
- What it does (paragraph)
- Key features (bullet list)
- Pricing
- Target audience

**Simulation settings** (also on this screen):
- Default LLM model, endpoint, API key
- Default batch size

**On submit**: saves product data to the DB, redirects to `/dashboard`.

**Access later**: via Settings panel on the dashboard.

### 2. Dashboard (`/dashboard`)

The main hub after setup. Shows at a glance: your product, your communities, your recent runs.

**Layout**:
- **Product bar** (top): product icon + name + tagline + Settings button
- **Communities section**: grid of community cards. Each card shows subreddit name, persona count, run count, archetype pills, and a "Simulate" button. Last card is always "+ Add community" (navigates to `/communities/new`).
- **Recent runs section**: table with columns: Run ID, Community, Grade (color-coded badge), Comments, Agents, When (relative time). Rows are clickable — navigate to `/simulate/:communityId?run=tag`.

**Settings panel** (slide-out from right): edit product info, LLM config, simulation defaults. Triggered by Settings button in product bar.

### 3. Add Community (`/communities/new`)

Dedicated page for creating a new community from a subreddit.

**Flow**:
1. Enter subreddit name in text input
2. Persona count slider (3–30, default 18)
3. Click "Generate" — scrapes subreddit via Reddit API, LLM generates personas
4. Review personas in a 2-column grid (name, archetype badge, bio, Edit/Remove buttons)
5. Click "Save Community" — stores in DB, redirects to `/dashboard`

Cancel returns to dashboard without saving.

If Reddit API keys are not configured, show a notice and disable generation.

Personas are stored in `community_profile` table and reused across all simulations for that community.

### 4. Simulation (`/simulate/:communityId`)

The simulation workspace, scoped to a specific community.

**Layout** (same 2-column as current):
- **Top bar**: `← Dashboard` link + community badge (e.g. `r/SaaS`) + persona count
- **Left sidebar**: agents slider, hours slider, estimated rounds/calls, progress bar (during sim), run history scoped to this community
- **Right panel**: Thread / Analysis tabs, Launch Simulation button, post textarea (editable for new sim, read-only for historical), comment thread, scorecard

This is essentially the current `index.html` layout with:
- Subreddit input/generate section removed (community is pre-selected)
- Top bar added with community context and back navigation
- Run history filtered to the current community
- `community_id` passed in the simulate request

## Routing

FastAPI catch-all: any non-`/api/` route serves `index.html`. Client-side History API router (~30 lines JS) maps URL → view:

| URL | View |
|-----|------|
| `/setup` | Setup form |
| `/dashboard` | Dashboard |
| `/communities/new` | Add Community |
| `/simulate/:communityId` | Simulation |
| `/simulate/:communityId?run=tag` | Simulation with historical run loaded |

On page load: check `GET /api/product` — if no product exists, redirect to `/setup`. Otherwise show `/dashboard`.

## Data Model Changes

New `product` table:
- `id`, `name`, `tagline`, `description`, `features`, `pricing`, `target_audience`, `llm_model`, `llm_base_url`, `llm_api_key`, `batch_size`, `created_at`, `updated_at`

Single row — only one product per installation.

## API Changes

New endpoints:
- `GET /api/product` — returns product data (or 404 if not set up)
- `POST /api/product` — create/update product data
- `GET /api/communities` — already exists, returns list with profile counts and run counts

Modified endpoints:
- `GET /api/runs` — add optional `?community_id=N` query param to filter by community

## Mockups

Static HTML mockups (temporary, delete after implementation):
- `simulation/static/mockup-dashboard.html`
- `simulation/static/mockup-add-community.html`
- `simulation/static/mockup-simulate.html`

## Compatibility

The simulation view is the most complex screen and is nearly identical to the current `index.html`. Changes needed:
- Remove the community-section div (subreddit input + generate + persona cards)
- Add a top bar with back link + community badge
- Filter run history by community_id
- Pass community_id from URL params into the simulate API call

All existing backend logic (simulation runner, scorecard, rewrite, extraction) is unchanged.
