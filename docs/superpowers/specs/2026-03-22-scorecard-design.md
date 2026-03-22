# Scorecard — Post-Simulation Insights

## Goal

Replace the current Analysis tab's free-form LLM prose with a structured, frequency-based scorecard that answers: **"How will Reddit receive my post?"** in under 10 seconds of reading.

## Design Decisions (from brainstorming)

- **Depth**: Actionable scorecard — score, top strengths, top problems, suggested fixes. No fluff.
- **Audience lens**: Archetype x sentiment cross-reference (founders were supportive, skeptics were critical, lurkers stayed silent).
- **Feature gap source**: From comments only — purely data-driven extraction, no LLM inference.
- **UI placement**: Replace the current Analysis tab content. Keep the "Rewrite Post" button at the bottom.
- **Data philosophy**: Frequencies, not quotes. "Pricing concerns: 4x" not "agent_jordan said pricing is high".

## Architecture — Approach B (SQL + Single LLM Classification)

Two data sources merged into one scorecard:

### Source 1: SQL Queries (hard numbers)

Queries against the OASIS SQLite DB (`results/{tag}.db`):

| Metric | Query Logic |
|---|---|
| Post score | `post.num_likes - post.num_dislikes` |
| Engagement rate | `COUNT(DISTINCT trace.user_id WHERE action != 'sign_up' AND action != 'do_nothing') / COUNT(DISTINCT user.user_id)` |
| Archetype participation | For each archetype: did they comment, like, dislike, or do_nothing? From `trace` + `comment` + `like` + `dislike` tables joined with archetype mapping |
| Total comments | `COUNT(*) FROM comment` |
| Total likes/dislikes | `post.num_likes`, `post.num_dislikes` |
| Silent agents | Users whose only trace actions are `sign_up`, `refresh`, `do_nothing` — they saw the post and chose not to engage |

### Source 2: Single LLM Classification Call

Input: all comment texts + their author archetypes.

Prompt asks the LLM to return structured JSON:

```json
{
  "comments": [
    {
      "comment_id": 1,
      "sentiment": "positive" | "negative" | "neutral",
      "topics": ["pricing", "privacy", "competition"],
      "is_objection": true | false,
      "is_feature_request": true | false,
      "feature_requested": "slack integration" | null
    }
  ]
}
```

Temperature: 0.0 (deterministic classification).

The LLM does NOT aggregate — it only classifies per-comment. Aggregation happens in Python by counting frequencies across the classified results.

### Merge Logic (Python)

1. Group LLM classifications by archetype (from profile mapping).
2. Count sentiment per archetype → build the matrix.
3. Count topics across all comments → rank by frequency → top themes.
4. Filter `is_objection == true`, group by topic → top problems.
5. Filter `sentiment == "positive"`, group by topic → top strengths.
6. Filter `is_feature_request == true`, group by `feature_requested` → missing features.
7. Compute reception grade: weighted formula from engagement rate, sentiment distribution, like/dislike ratio.

### Reception Grade Formula

```
grade = (
    0.4 * supportive_pct +
    0.3 * engagement_rate +
    0.2 * (likes / (likes + dislikes + 1)) +
    0.1 * (1 - silent_agent_pct)
)
```

Map to letter: A+ (>90), A (>80), B+ (>70), B (>60), C+ (>50), C (>40), D (>30), F (<=30).

## Scorecard UI Layout

Six sections rendered as cards in the Analysis tab:

### 1. Reception Header
- Letter grade (large, colored: green A/B, yellow C, red D/F)
- Numeric score (e.g., 7.2/10)
- One-line summary: "Based on: X likes, Y dislikes, Z% engagement"

### 2. Archetype x Sentiment Matrix
A grid/table:
- Rows: each archetype present in the simulation (Founders, Skeptics, Indie Devs, HR, VCs, Lurkers, etc.)
- Columns: Positive, Neutral, Negative, Silent
- Cells: count of agents in that bucket
- "Silent" column for archetypes that had agents but none engaged

### 3. Top Themes (by frequency)
Horizontal bars or simple list:
- Theme name + mention count + color (green if mostly positive context, red if mostly negative)
- Max 5 themes, sorted by frequency descending

### 4. Strengths & Problems (side by side)
Two columns:
- Left: Top 3 strengths — topic + frequency (e.g., "Privacy-first approach (3x)")
- Right: Top 3 problems — topic + frequency (e.g., "Pricing too high (4x)")

### 5. Missing Features
List of explicitly requested features from comments:
- Feature name + how many agents mentioned it
- Only shown if at least 1 feature request was detected; hidden otherwise

### 6. Rewrite Button
Keep existing "Rewrite Post Based on Feedback" functionality. The rewrite LLM call now receives the scorecard JSON as context instead of raw comments, producing a more targeted rewrite.

## Backend Changes

### New file: `scripts/generate_scorecard.py`

Functions:
- `query_engagement_metrics(db_path) -> dict` — SQL queries for hard numbers
- `query_archetype_participation(db_path, profiles) -> dict` — who did what, by archetype
- `classify_comments(comments, model_config) -> list[dict]` — single LLM call, returns per-comment classification
- `build_scorecard(metrics, participation, classifications) -> ScorecardData` — merge into final structure
- `compute_grade(scorecard) -> str` — letter grade from formula

Returns a `ScorecardData` TypedDict with all sections pre-computed as JSON-serializable data.

### Server changes: `server.py`

- Replace `/api/analyze/{tag}` response with scorecard JSON
- Or add new endpoint `/api/scorecard/{tag}` and deprecate analyze
- The rewrite endpoint stays but receives scorecard data as input

### UI changes: `static/index.html`

- Replace Analysis tab markup with scorecard card layout
- Render from JSON (no markdown parsing needed — structured data → HTML)
- Keep the rewrite button at bottom, wire it to pass scorecard context

## Data Flow

```
User clicks "Analyze" on Analysis tab
  → POST /api/scorecard/{tag}
    → query_engagement_metrics(db_path)     [SQL]
    → query_archetype_participation(db_path) [SQL]
    → classify_comments(comments)            [1 LLM call]
    → build_scorecard(metrics, participation, classifications)
    → compute_grade(scorecard)
  ← JSON: { grade, matrix, themes, strengths, problems, missing_features }
  → UI renders structured cards from JSON

User clicks "Rewrite Post"
  → POST /api/rewrite/{tag}
    → receives scorecard JSON + original post
    → 1 LLM call to rewrite
  ← { improved_post: "..." }
```

## What Changes vs. Current System

| Aspect | Before | After |
|---|---|---|
| Analysis trigger | "Analyze & Generate Improved Post" (1 button, does both) | "Analyze" shows scorecard instantly; "Rewrite" is a separate action |
| Analysis output | Markdown prose wall | Structured JSON → rendered cards |
| LLM calls for analysis | 1 (free-form analysis) | 1 (structured classification) |
| LLM calls for rewrite | 1 (bundled with analysis) | 1 (separate, triggered by button) |
| Data backing | LLM-only | SQL metrics + LLM classification |
| Per-archetype view | None | Full matrix |
| Frequencies | Mentioned in prose | Explicit counts |
| Missing features | LLM-inferred | Extracted from comments only |
| Silent agents | Not shown | Explicitly surfaced |

## Files Changed

- `scripts/generate_scorecard.py` — NEW: scorecard generation logic
- `server.py` — Replace/add scorecard endpoint, split rewrite endpoint
- `static/index.html` — Replace Analysis tab with scorecard cards
- `scripts/analyze_and_rewrite.py` — Keep `rewrite()`, deprecate `analyze()`

## Testing

- Unit tests for `query_engagement_metrics` with a test DB
- Unit tests for `build_scorecard` with mock classification data
- Unit test for `compute_grade` edge cases (all positive, all negative, no comments, no engagement)
- Integration test: full flow from DB → scorecard JSON → verify all sections populated
