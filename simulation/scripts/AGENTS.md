# scripts/ — Simulation Pipeline

9 modules orchestrating the simulation lifecycle. Imported by `server.py` as package (`import scripts.analyze_and_rewrite`). The `__init__.py` MUST exist.

## PIPELINE EXECUTION ORDER

```
POST /api/simulate
  → server.py spawns subprocess
    → run_simulation.py (OASIS multi-agent sim)
      → humanize_comments() (batch LLM rewrite)
      → extract_oasis_results() → app DB

POST /api/scorecard/{tag}  (on-demand, cached)
  → generate_scorecard.py
    → query metrics → classify comments (LLM) → build grade

POST /api/analyze/{tag}  (on-demand)
  → analyze_and_rewrite.py
    → analyze feedback → rewrite post (LLM)

GET /api/thread/{tag}
  → generate_html.py → Reddit-style HTML
```

## SCRIPT MAP

| Script | Lines | Purpose | LLM Temp |
|--------|-------|---------|----------|
| `run_simulation.py` | 519 | OASIS orchestration, interviews, humanization | 0.8 |
| `generate_scorecard.py` | 931 | Engagement metrics, sentiment, grading (A+ to F) | 0.0 |
| `analyze_and_rewrite.py` | 118 | Comment analysis + post rewriting | 0.3 |
| `generate_community.py` | 237 | Reddit scraping (PRAW) + persona generation | 0.7 |
| `generate_html.py` | 219 | Reddit-style HTML thread rendering | — |
| `generate_report.py` | 441 | Text-format engagement report | 0.0 |
| `compare_runs.py` | 357 | Multi-run comparison + winner selection | 0.0 |
| `parse_post.py` | 69 | Markdown post → `{title, body}` | — |

## DUAL DATABASE PATTERN

Scripts read/write TWO separate SQLite databases:

| Database | Location | Written By | Read By |
|----------|----------|-----------|---------|
| **App DB** (`post-pilot.db`) | User's `.post-pilot/` | `run_simulation` (comments, agents, interviews), `generate_scorecard` (scorecard) | `generate_scorecard`, `generate_html` |
| **OASIS DB** (`results/{tag}.db`) | User's `.post-pilot/` | OASIS framework (posts, traces), `humanize_comments` | `analyze_and_rewrite`, `generate_report`, `compare_runs` |

`extract_oasis_results()` in `db.py` bridges OASIS DB → App DB after simulation.

## SHARED PATTERNS

**LLM model creation** (identical in all LLM-using scripts):
```python
ModelFactory.create(
    model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
    model_type=os.getenv("LLM_MODEL"),
    api_key=os.getenv("LLM_API_KEY"),
    url=os.getenv("LLM_BASE_URL"),
    model_config_dict={"temperature": <varies>},
)
```

**JSON parsing from LLM** — all strip markdown fences:
```python
text = raw.strip()
if text.startswith("```"):
    text = text.split("\n", 1)[1].rsplit("```", 1)[0]
return json.loads(text)
```

**Batch LLM calls** — scorecard batches 5 comments, humanizer batches 25.

## KEY ALGORITHMS

- **Grade formula** (generate_scorecard.py): `0.4×supportive% + 0.3×engagement_rate + 0.2×like_ratio + 0.1×(100-silent%)`
- **Agent scheduling** (run_simulation.py): MiroFish-style — `get_active_agents_for_hour()` uses time multipliers (peak 1.5×, off-peak 0.1×, normal 0.7×) combined with per-archetype activity levels
- **Profile selection** (db.py): Round-robin across archetypes to ensure balanced representation

## ANTI-PATTERNS

- **NEVER remove `__init__.py`** — breaks `import scripts.*` in server.py
- **NEVER call scripts directly from CLI in production** — server.py manages env vars and DB paths
- **NEVER skip `extract_oasis_results()`** — app DB needs simulation data for scorecard/UI
- **NEVER hardcode LLM temp** — each script uses purpose-specific temperature (see table above)
