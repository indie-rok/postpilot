# Reddit Post Simulation — FlowPulse Launch Post

**Date**: 2026-03-22
**Status**: Approved
**Approach**: OASIS-direct with custom profiles, CLI scripts

---

## Goal

Simulate how the FlowPulse launch post (`post.md`) would perform on r/SaaS using OASIS's Reddit simulation engine. Measure engagement, collect qualitative feedback from LLM-powered agents, and A/B test post variants to find the version that lands best.

**Source artifacts**: `post.md` and `company.md` live in the repo root. `posts/original.txt` is the parsed runtime input extracted from `post.md` by `parse_post.py`. Variants are hand-edited copies of `original.txt`.

---

## Architecture

```
INPUT                    SIMULATE                  ANALYZE
─────                    ────────                  ───────
post.md ──parse──▶   Load 18 agents          Query SQLite DB
profiles.json ──▶    Seed post                Sentiment classify
config.py ──▶        Run 10 rounds ──▶ .db    Theme extraction
                     (OASIS Reddit engine)    Comparison tables
```

Three scripts, three concerns:

| Script | Input | Output | Purpose |
|--------|-------|--------|---------|
| `run_simulation.py` | Post text + profiles + config | SQLite DB in `results/` | Run one simulation |
| `compare_runs.py` | Multiple SQLite DBs | Comparison report | A/B analysis across variants |
| `generate_report.py` | Single SQLite DB | Detailed report | Deep dive into one run |

Each run produces an isolated SQLite DB named by tag: `results/{tag}.db` (e.g., `results/v1-original.db`). The `--tag` flag is required and determines the output filename.

---

## Agent Personas — 18 Agents, 8 Archetypes

| # | Archetype | Count | Stance | Behavior |
|---|-----------|-------|--------|----------|
| 1 | SaaS Founder (early stage) | 3 | Supportive | Shares experience, asks about metrics, relates to the struggle |
| 2 | SaaS Founder (scaled) | 2 | Neutral-supportive | Offers advice, questions scalability, compares to existing tools |
| 3 | Skeptical PM/Buyer | 3 | Opposing-neutral | Pushes back on claims, asks "how different from X?", questions pricing |
| 4 | Indie Hacker | 2 | Neutral | Price-sensitive, interested in tech, asks about stack and margins |
| 5 | HR / People Ops | 2 | Supportive | Target buyer. Asks about implementation, integrations, ROI |
| 6 | Lurker | 3 | Mixed | Vote only, no comments. 2 lean positive, 1 lean negative |
| 7 | Community Regular | 2 | Neutral-opposing | Polices self-promo. Calls out salesy posts |
| 8 | VC / Growth Advisor | 1 | Supportive | Asks about TAM, retention, funding |

**Stance distribution**: ~6 supportive, ~5 neutral, ~4 skeptical, ~3 silent voters.

### Profile Format

Each agent is defined in `profiles/r_saas_community.json`:

```json
{
  "username": "jordan_prodmgmt",
  "realname": "Jordan Reeves",
  "bio": "Sr. PM at a Series C SaaS. I've seen 50 'AI-powered' tools. Show me the data.",
  "persona": "Jordan is a senior product manager at a 200-person B2B SaaS company. She's evaluated dozens of HR and engagement tools and is deeply skeptical of vague AI claims. She values concrete metrics, transparent pricing, and proof of differentiation. She frequently comments on r/SaaS posts to challenge founders who oversell. She respects founders who share honest numbers and admit weaknesses. She dislikes posts that feel like ads disguised as stories. MBTI: INTP. She comments often but rarely upvotes.",
  "age": 29,
  "gender": "female",
  "mbti": "INTP",
  "country": "US",
  "profession": "Product Management",
  "interested_topics": ["SaaS", "B2B", "Product", "Analytics"]
}
```

---

## Simulation Configuration

### Platform Config

```python
platform_config = {
    "platform": "reddit",
    "recsys_type": "reddit",
    "allow_self_rating": False,
    "show_score": True,
    "max_rec_post_len": 20,
    "refresh_rec_post_count": 5,
}
```

### Temporal Model — 10 Rounds (~24 Hours)

| Round | Simulated Time | Phase |
|-------|---------------|-------|
| 1 | 0-1h | Post goes live. Early votes + comments. |
| 2-3 | 1-4h | Peak discovery. Hot-score ranking active. Most comments. |
| 4-6 | 4-12h | Engagement plateau. Replies to comments. Skeptics arrive. |
| 7-9 | 12-20h | Long tail. Lurkers vote. Thread cools. |
| 10 | 20-24h | Final state. Post settles. |

### Agent Activity Config (per archetype)

| Archetype | Activity Level | Comments/Round | Vote Probability | Active Rounds |
|-----------|---------------|----------------|-----------------|---------------|
| SaaS Founder (early) | 0.7 | 1-2 | 0.8 | 1-6 |
| SaaS Founder (scaled) | 0.5 | 0-1 | 0.6 | 2-5 |
| Skeptical PM | 0.8 | 1-2 | 0.4 | 2-7 |
| Indie Hacker | 0.5 | 0-1 | 0.7 | 1-8 |
| HR / People Ops | 0.6 | 1 | 0.7 | 3-8 |
| Lurker | 0.3 | 0 | 0.9 | 1-10 |
| Community Regular | 0.7 | 1 | 0.5 | 1-4 |
| VC / Growth | 0.4 | 0-1 | 0.6 | 4-8 |

---

## LLM Backend — MiniMax 2.7

Via CAMEL's OpenAI-compatible adapter:

```python
from camel.models import ModelFactory
from camel.types import ModelPlatformType

model = ModelFactory.create(
    model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
    model_type="MiniMax-Text-01",
    api_key=os.getenv("MINIMAX_API_KEY"),
    url="https://api.minimax.chat/v1",
    model_config_dict={"temperature": 0.8},
)
```

**Cost estimate**: 15-20 agents x 10 rounds = ~150-200 LLM calls per run.

---

## A/B Testing

Three post variants for initial comparison:

| Tag | Variant | What Changes |
|-----|---------|-------------|
| `v1-original` | `original.txt` | Direct parse of `post.md` as-is |
| `v2-punchy-title` | `variant_punchy_title.txt` | Shorter, hookier title. Less "here's what we learned" framing |
| `v3-lower-pricing` | `variant_lower_pricing.txt` | Starter plan at $2/user/mo instead of $4 |

Run each variant independently, then compare via `compare_runs.py`. All commands run from `/simulation/`.

```bash
python scripts/run_simulation.py --post posts/original.txt --tag "v1-original"
python scripts/run_simulation.py --post posts/variant_punchy_title.txt --tag "v2-punchy-title"
python scripts/run_simulation.py --post posts/variant_lower_pricing.txt --tag "v3-lower-pricing"
python scripts/compare_runs.py results/v1-original.db results/v2-punchy-title.db results/v3-lower-pricing.db
```

---

## Output — Report Format

### Single Run Report (`generate_report.py`)

Outputs to stdout (or file with `--output` flag):

1. **Engagement Summary**: Final score (upvotes - downvotes), comment count, engagement rate (agents who took any action / total agents)
2. **Sentiment Breakdown**: Supportive / neutral / skeptical percentages (via LLM classification)
3. **Top Themes**: Recurring topics extracted from comments (via single LLM call)
4. **Agent-by-Agent Reactions**: Table of each agent's action + key comment
5. **Round-by-Round Engagement**: ASCII histogram of score and comment progression
6. **Actionable Insights**: LLM-generated recommendations based on the data

### Multi-Run Comparison (`compare_runs.py`)

Side-by-side table:

- Final score per variant
- Comment count per variant
- Sentiment distribution per variant
- Key theme differences
- Winner designation — **determined by highest final score (upvotes - downvotes)**. Ties broken by highest supportive comment percentage. No composite scoring — keep it simple.

### Analysis Implementation

- **Engagement metrics**: Direct SQLite queries on `post`, `comment`, `like`, `dislike` tables
- **Sentiment classification**: Batch LLM call — feed all comments, classify each as supportive/neutral/skeptical
- **Theme extraction**: Single LLM call — "given these comments, what are the top 5 recurring themes?"
- **Round-by-round**: Query `trace` table grouped by round/timestamp

---

## File Structure

```
/simulation/
├── profiles/
│   └── r_saas_community.json          # 18 agent personas (~300 lines)
├── posts/
│   ├── original.txt                    # Parsed from post.md
│   ├── variant_punchy_title.txt
│   └── variant_lower_pricing.txt
├── config/
│   └── simulation_config.py            # Platform config, activity levels (~80 lines)
├── scripts/
│   ├── run_simulation.py               # Core OASIS runner (~150 lines)
│   ├── compare_runs.py                 # Multi-run comparison (~120 lines)
│   ├── generate_report.py              # Single-run deep dive (~200 lines)
│   └── parse_post.py                   # Markdown → plain text (~40 lines)
├── results/
│   └── .gitkeep
├── requirements.txt
├── .env.example
└── README.md
```

**Total**: ~900 lines Python + ~300 lines JSON profiles.

---

## Dependencies

```
camel-ai[tools]>=0.2.78
camel-oasis>=0.2.5
python-dotenv
```

---

## Out of Scope

- No web UI or dashboard
- No knowledge graph / Zep integration
- No persistent server
- No auto-generated personas
- No MiroFish-style report agent (simpler LLM-assisted analysis instead)

---

## Success Criteria

1. `run_simulation.py` completes a 10-round simulation and writes a valid SQLite DB
2. `generate_report.py` produces a readable report with engagement, sentiment, themes, and per-agent breakdown
3. `compare_runs.py` produces a side-by-side table across 3+ variants
4. All 18 agents behave consistently with their personas (no out-of-character actions)
5. MiniMax 2.7 works as the LLM backend via CAMEL's OpenAI-compatible adapter
