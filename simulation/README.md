# Reddit Post Simulation

Simulate how a SaaS launch post performs on r/SaaS using [OASIS](https://github.com/camel-ai/oasis) — an LLM-powered social media simulation framework. 18 AI agents with distinct personas (founders, skeptics, lurkers, HR buyers, etc.) react to your post. Run multiple variants and compare engagement to find what lands best.

## Prerequisites

- Python 3.11+
- MiniMax API key ([minimax.io](https://minimax.io))

## Setup

```bash
cd simulation
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your MINIMAX_API_KEY
```

## Usage

### Run a simulation

```bash
python scripts/run_simulation.py --post posts/original.txt --tag "v1-original"
```

This runs 10 rounds (~24h simulated) with 18 agents and saves results to `results/v1-original.db`.

### Generate a report

```bash
# Full report with LLM-powered sentiment and theme analysis
python scripts/generate_report.py results/v1-original.db

# Quick report without LLM calls (SQL metrics only)
python scripts/generate_report.py results/v1-original.db --skip-llm

# Save to file
python scripts/generate_report.py results/v1-original.db --output results/v1-report.txt
```

### A/B test post variants

```bash
python scripts/run_simulation.py --post posts/original.txt --tag "v1-original"
python scripts/run_simulation.py --post posts/variant_punchy_title.txt --tag "v2-punchy-title"
python scripts/run_simulation.py --post posts/variant_lower_pricing.txt --tag "v3-lower-pricing"

python scripts/compare_runs.py results/v1-original.db results/v2-punchy-title.db results/v3-lower-pricing.db
```

### Parse a new post from markdown

```bash
python scripts/parse_post.py ../post.md --output posts/my_new_post.txt
```

## Running tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

## Creating new variants

1. Copy `posts/original.txt` to `posts/variant_my_change.txt`
2. Edit the specific part you want to test (title, pricing, tone, etc.)
3. Run the simulation with a new tag
4. Compare against other runs

## Customizing agents

Edit `profiles/r_saas_community.json`. Each agent has:

- `username` — must contain an archetype prefix (`founder_early`, `skeptic`, `lurker`, etc.)
- `persona` — detailed behavioral description (200+ chars) that drives LLM behavior
- `mbti`, `age`, `gender`, `country` — demographic attributes
- `interested_topics` — content relevance signals

The `persona` field is the most important — it determines how the agent reacts to posts.

## Project structure

```
simulation/
├── profiles/r_saas_community.json   # 18 agent personas
├── posts/                           # Post variants for A/B testing
├── config/simulation_config.py      # Platform & activity configs
├── scripts/
│   ├── run_simulation.py            # Core OASIS simulation runner
│   ├── generate_report.py           # Single-run analysis
│   ├── compare_runs.py              # Multi-run A/B comparison
│   └── parse_post.py                # Markdown → plain text
├── results/                         # SQLite DBs (one per run)
└── tests/                           # pytest test suite
```

## Cost estimate

~150-200 LLM calls per simulation run (18 agents x 10 rounds). With MiniMax pricing, roughly $0.05-0.15 per run.
