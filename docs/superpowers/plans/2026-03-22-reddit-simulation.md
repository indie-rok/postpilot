# Reddit Post Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI-based Reddit post simulation using OASIS that tests how the FlowPulse launch post performs on r/SaaS with 18 LLM-powered agents, supporting A/B variant comparison.

**Architecture:** Three Python scripts (`run_simulation.py`, `generate_report.py`, `compare_runs.py`) backed by OASIS's Reddit simulation engine with MiniMax 2.7 as the LLM. Agent personas are hand-crafted JSON profiles. Each simulation run outputs a SQLite DB; analysis scripts query those DBs and use LLM calls for sentiment/theme extraction.

**Tech Stack:** Python 3.11+, camel-ai, camel-oasis, MiniMax 2.7 (OpenAI-compatible API), SQLite, pytest

**Spec:** `docs/superpowers/specs/2026-03-22-reddit-simulation-design.md`

---

## File Map

| File | Responsibility | Created/Modified |
|------|---------------|-----------------|
| `simulation/requirements.txt` | Python dependencies | Create |
| `simulation/.env.example` | API key placeholder | Create |
| `simulation/scripts/parse_post.py` | Markdown → plain text extraction (title + body) | Create |
| `simulation/profiles/r_saas_community.json` | 18 agent personas with full profiles | Create |
| `simulation/config/simulation_config.py` | Platform config, activity configs, model factory | Create |
| `simulation/scripts/run_simulation.py` | Core OASIS runner: load agents, seed post, run rounds, save DB | Create |
| `simulation/scripts/generate_report.py` | Single-run analysis: engagement, sentiment, themes, per-agent | Create |
| `simulation/scripts/compare_runs.py` | Multi-run A/B comparison with winner designation | Create |
| `simulation/posts/original.txt` | Parsed from `post.md` | Create |
| `simulation/posts/variant_punchy_title.txt` | A/B variant: shorter, hookier title | Create |
| `simulation/posts/variant_lower_pricing.txt` | A/B variant: $2/user instead of $4 | Create |
| `simulation/results/.gitkeep` | Empty dir placeholder | Create |
| `simulation/tests/test_parse_post.py` | Tests for markdown parser | Create |
| `simulation/tests/test_config.py` | Tests for config loading | Create |
| `simulation/tests/test_report.py` | Tests for report generation (mock DB) | Create |
| `simulation/tests/test_compare.py` | Tests for comparison logic (mock DBs) | Create |
| `simulation/README.md` | Usage documentation | Create |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `simulation/requirements.txt`
- Create: `simulation/.env.example`
- Create: `simulation/results/.gitkeep`
- Create: `simulation/tests/__init__.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p simulation/{profiles,posts,config,scripts,results,tests}
touch simulation/results/.gitkeep
touch simulation/tests/__init__.py
```

- [ ] **Step 2: Create requirements.txt**

Create `simulation/requirements.txt`:

```
camel-ai[tools]>=0.2.78
camel-oasis>=0.2.5
python-dotenv>=1.0.0
pytest>=8.0.0
```

- [ ] **Step 3: Create .env.example**

Create `simulation/.env.example`:

```
MINIMAX_API_KEY=your-minimax-api-key-here
```

- [ ] **Step 4: Create Python virtual environment and install dependencies**

```bash
cd simulation
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Expected: All packages install without errors. `camel-oasis` pulls in OASIS.

- [ ] **Step 5: Verify OASIS is importable**

```bash
cd simulation
source .venv/bin/activate
python -c "import oasis; print('OASIS version:', oasis.__version__)"
```

Expected: Prints OASIS version without import errors.

- [ ] **Step 6: Commit**

```bash
git add simulation/
git commit -m "chore: scaffold reddit simulation project with dependencies"
```

---

## Task 2: Post Parser (`parse_post.py`)

**Files:**
- Create: `simulation/tests/test_parse_post.py`
- Create: `simulation/scripts/parse_post.py`

- [ ] **Step 1: Write the failing test**

Create `simulation/tests/test_parse_post.py`:

```python
"""Tests for parse_post.py — markdown to plain text extraction."""
import os
import tempfile
import pytest

# Add scripts to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from parse_post import parse_markdown_post


SAMPLE_MARKDOWN = """# r/SaaS

---

**We built a tool that predicts employee burnout. Here's what we learned.**

---

Hey r/SaaS — Maya here, co-founder of FlowPulse.

Quick background: I spent 4 years running People Ops.

## The problem

Remote teams are burning out in silence.

## What we built

**FlowPulse** is a lightweight pulse check platform.

- **Starter** — $4/user/mo
- **Growth** — $8/user/mo

[flowpulse.io](https://flowpulse.io)
"""


def test_parse_extracts_title():
    result = parse_markdown_post(SAMPLE_MARKDOWN)
    assert result["title"] == "We built a tool that predicts employee burnout. Here's what we learned."


def test_parse_extracts_body():
    result = parse_markdown_post(SAMPLE_MARKDOWN)
    body = result["body"]
    # Should contain the main content
    assert "Maya here, co-founder of FlowPulse" in body
    assert "Remote teams are burning out" in body
    # Should strip markdown formatting
    assert "**" not in body
    assert "##" not in body


def test_parse_preserves_list_items():
    result = parse_markdown_post(SAMPLE_MARKDOWN)
    body = result["body"]
    assert "$4/user/mo" in body
    assert "$8/user/mo" in body


def test_parse_strips_links_keeps_text():
    result = parse_markdown_post(SAMPLE_MARKDOWN)
    body = result["body"]
    assert "flowpulse.io" in body
    assert "[" not in body
    assert "](" not in body


def test_parse_from_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(SAMPLE_MARKDOWN)
        f.flush()
        result = parse_markdown_post(open(f.name).read())
    os.unlink(f.name)
    assert result["title"] != ""
    assert result["body"] != ""
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd simulation
source .venv/bin/activate
python -m pytest tests/test_parse_post.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'parse_post'`

- [ ] **Step 3: Write the implementation**

Create `simulation/scripts/parse_post.py`:

```python
"""Parse a Reddit-style markdown post into title + body plain text."""
import re
import argparse


def parse_markdown_post(markdown: str) -> dict[str, str]:
    """Extract title and body from a Reddit-style markdown post.

    Title: First bold line (**text**) that looks like a post title.
    Body: Everything after the title, with markdown formatting stripped.

    Returns:
        {"title": str, "body": str}
    """
    lines = markdown.strip().split("\n")

    title = ""
    title_line_idx = -1

    # Find the first bold line (Reddit post title pattern)
    for i, line in enumerate(lines):
        stripped = line.strip()
        match = re.match(r"^\*\*(.+)\*\*$", stripped)
        if match and len(match.group(1)) > 20:  # Skip short bold text
            title = match.group(1)
            title_line_idx = i
            break

    # Body = everything after the title, stripped of markdown
    body_lines = lines[title_line_idx + 1:] if title_line_idx >= 0 else lines
    body = "\n".join(body_lines)
    body = _strip_markdown(body)

    return {"title": title, "body": body.strip()}


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting, keep plain text."""
    # Remove horizontal rules
    text = re.sub(r"^---+\s*$", "", text, flags=re.MULTILINE)
    # Remove headers (## Header -> Header)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold/italic
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    # Convert links [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove leading list markers but keep content
    text = re.sub(r"^[-*]\s+", "", text, flags=re.MULTILINE)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def main():
    parser = argparse.ArgumentParser(description="Parse markdown post to plain text")
    parser.add_argument("input", help="Path to markdown file")
    parser.add_argument("--output", help="Output file path (default: stdout)")
    args = parser.parse_args()

    with open(args.input, "r") as f:
        content = f.read()

    result = parse_markdown_post(content)

    output_text = f"{result['title']}\n\n{result['body']}"

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_text)
        print(f"Written to {args.output}")
    else:
        print(output_text)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd simulation
source .venv/bin/activate
python -m pytest tests/test_parse_post.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add simulation/scripts/parse_post.py simulation/tests/test_parse_post.py
git commit -m "feat: add markdown post parser with tests"
```

---

## Task 3: Agent Personas

**Files:**
- Create: `simulation/profiles/r_saas_community.json`
- Create: `simulation/tests/test_profiles.py`

- [ ] **Step 1: Write the validation test**

Create `simulation/tests/test_profiles.py`:

```python
"""Tests for agent profile data integrity."""
import json
import os
import pytest

PROFILES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "profiles", "r_saas_community.json"
)

REQUIRED_FIELDS = [
    "username", "realname", "bio", "persona",
    "age", "gender", "mbti", "country",
    "profession", "interested_topics"
]

VALID_MBTI = [
    "INTJ", "INTP", "ENTJ", "ENTP",
    "INFJ", "INFP", "ENFJ", "ENFP",
    "ISTJ", "ISFJ", "ESTJ", "ESFJ",
    "ISTP", "ISFP", "ESTP", "ESFP",
]


@pytest.fixture
def profiles():
    with open(PROFILES_PATH) as f:
        return json.load(f)


def test_has_18_agents(profiles):
    assert len(profiles) == 18


def test_all_required_fields_present(profiles):
    for i, profile in enumerate(profiles):
        for field in REQUIRED_FIELDS:
            assert field in profile, f"Agent {i} ({profile.get('username', '?')}) missing '{field}'"


def test_usernames_are_unique(profiles):
    usernames = [p["username"] for p in profiles]
    assert len(usernames) == len(set(usernames))


def test_valid_mbti_types(profiles):
    for profile in profiles:
        assert profile["mbti"] in VALID_MBTI, (
            f"{profile['username']} has invalid MBTI: {profile['mbti']}"
        )


def test_persona_is_detailed(profiles):
    """Persona should be at least 200 chars for meaningful LLM behavior."""
    for profile in profiles:
        assert len(profile["persona"]) >= 200, (
            f"{profile['username']} persona too short: {len(profile['persona'])} chars"
        )


def test_gender_values(profiles):
    for profile in profiles:
        assert profile["gender"] in ("male", "female", "other"), (
            f"{profile['username']} has invalid gender: {profile['gender']}"
        )


def test_age_range(profiles):
    for profile in profiles:
        assert 18 <= profile["age"] <= 70, (
            f"{profile['username']} has unrealistic age: {profile['age']}"
        )


def test_interested_topics_non_empty(profiles):
    for profile in profiles:
        assert len(profile["interested_topics"]) >= 1, (
            f"{profile['username']} has no interested_topics"
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd simulation
source .venv/bin/activate
python -m pytest tests/test_profiles.py -v
```

Expected: FAIL — FileNotFoundError (profiles JSON doesn't exist yet).

- [ ] **Step 3: Create the 18 agent profiles**

Create `simulation/profiles/r_saas_community.json` with all 18 agents. Each persona must be 200+ characters, detailed, and behaviorally distinct. Follow the archetype distribution from the spec:

- 3x SaaS Founder (early stage) — supportive
- 2x SaaS Founder (scaled) — neutral-supportive
- 3x Skeptical PM/Buyer — opposing-neutral
- 2x Indie Hacker — neutral
- 2x HR / People Ops — supportive
- 3x Lurker — mixed (2 positive, 1 negative)
- 2x Community Regular — neutral-opposing
- 1x VC / Growth Advisor — supportive

Each profile must include: `username`, `realname`, `bio`, `persona`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`.

The `persona` field is the most important — it drives the LLM's behavior. Include:
- Professional background and experience level
- Attitude toward SaaS launch posts on Reddit
- What they look for in a product (or what turns them off)
- Commenting style and engagement patterns
- Specific triggers that make them upvote, downvote, or comment

For lurkers: persona should explicitly state they only vote, never comment.
For community regulars: persona should describe their self-promo detection instincts.

- [ ] **Step 4: Run profile validation tests**

```bash
cd simulation
source .venv/bin/activate
python -m pytest tests/test_profiles.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add simulation/profiles/r_saas_community.json simulation/tests/test_profiles.py
git commit -m "feat: add 18 r/SaaS agent personas with validation tests"
```

---

## Task 4: Simulation Config

**Files:**
- Create: `simulation/config/__init__.py`
- Create: `simulation/config/simulation_config.py`
- Create: `simulation/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `simulation/tests/test_config.py`:

```python
"""Tests for simulation configuration."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.simulation_config import (
    PLATFORM_CONFIG,
    ACTIVITY_CONFIGS,
    NUM_ROUNDS,
    ARCHETYPE_NAMES,
)


def test_platform_config_is_reddit():
    assert PLATFORM_CONFIG["recsys_type"] == "reddit"


def test_platform_config_no_self_rating():
    assert PLATFORM_CONFIG["allow_self_rating"] is False


def test_platform_config_shows_score():
    assert PLATFORM_CONFIG["show_score"] is True


def test_num_rounds():
    assert NUM_ROUNDS == 10


def test_activity_configs_cover_all_archetypes():
    for name in ARCHETYPE_NAMES:
        assert name in ACTIVITY_CONFIGS, f"Missing activity config for '{name}'"


def test_activity_config_structure():
    required_keys = {"activity_level", "comments_per_round", "vote_probability", "active_rounds"}
    for name, config in ACTIVITY_CONFIGS.items():
        for key in required_keys:
            assert key in config, f"'{name}' missing key '{key}'"


def test_activity_level_range():
    for name, config in ACTIVITY_CONFIGS.items():
        assert 0.0 <= config["activity_level"] <= 1.0, (
            f"'{name}' activity_level out of range: {config['activity_level']}"
        )


def test_active_rounds_within_simulation():
    for name, config in ACTIVITY_CONFIGS.items():
        low, high = config["active_rounds"]
        assert 1 <= low <= NUM_ROUNDS, f"'{name}' active_rounds low out of range"
        assert low <= high <= NUM_ROUNDS, f"'{name}' active_rounds high out of range"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd simulation
source .venv/bin/activate
python -m pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the config module**

Create `simulation/config/__init__.py`:

```python
```

Create `simulation/config/simulation_config.py`:

```python
"""Simulation configuration for r/SaaS Reddit simulation."""

# OASIS Reddit platform configuration
PLATFORM_CONFIG = {
    "recsys_type": "reddit",
    "allow_self_rating": False,
    "show_score": True,
    "max_rec_post_len": 20,
    "refresh_rec_post_count": 5,
}

NUM_ROUNDS = 10

# Archetype names must match profile groupings
ARCHETYPE_NAMES = [
    "saas_founder_early",
    "saas_founder_scaled",
    "skeptical_pm",
    "indie_hacker",
    "hr_people_ops",
    "lurker",
    "community_regular",
    "vc_growth",
]

# Activity configuration per archetype
# comments_per_round: (min, max) range
# active_rounds: (first_round, last_round) 1-indexed
ACTIVITY_CONFIGS = {
    "saas_founder_early": {
        "activity_level": 0.7,
        "comments_per_round": (1, 2),
        "vote_probability": 0.8,
        "active_rounds": (1, 6),
    },
    "saas_founder_scaled": {
        "activity_level": 0.5,
        "comments_per_round": (0, 1),
        "vote_probability": 0.6,
        "active_rounds": (2, 5),
    },
    "skeptical_pm": {
        "activity_level": 0.8,
        "comments_per_round": (1, 2),
        "vote_probability": 0.4,
        "active_rounds": (2, 7),
    },
    "indie_hacker": {
        "activity_level": 0.5,
        "comments_per_round": (0, 1),
        "vote_probability": 0.7,
        "active_rounds": (1, 8),
    },
    "hr_people_ops": {
        "activity_level": 0.6,
        "comments_per_round": (0, 1),
        "vote_probability": 0.7,
        "active_rounds": (3, 8),
    },
    "lurker": {
        "activity_level": 0.3,
        "comments_per_round": (0, 0),
        "vote_probability": 0.9,
        "active_rounds": (1, 10),
    },
    "community_regular": {
        "activity_level": 0.7,
        "comments_per_round": (0, 1),
        "vote_probability": 0.5,
        "active_rounds": (1, 4),
    },
    "vc_growth": {
        "activity_level": 0.4,
        "comments_per_round": (0, 1),
        "vote_probability": 0.6,
        "active_rounds": (4, 8),
    },
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd simulation
source .venv/bin/activate
python -m pytest tests/test_config.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add simulation/config/ simulation/tests/test_config.py
git commit -m "feat: add simulation config with activity levels per archetype"
```

---

## Task 5: Simulation Runner (`run_simulation.py`)

**Files:**
- Create: `simulation/scripts/run_simulation.py`

This is the core integration script. It wires OASIS together. Because it depends on LLM calls and OASIS internals, we skip unit tests here — the end-to-end smoke test (Task 10) validates it.

- [ ] **Step 0: Inspect installed OASIS API surface**

Before writing any code, verify the actual OASIS API against what the librarian reported. Run this in the venv:

```bash
cd simulation
source .venv/bin/activate
python -c "
import oasis
import inspect

# Check top-level exports
print('=== oasis exports ===')
print([x for x in dir(oasis) if not x.startswith('_')])

# Check if generate_reddit_agent_graph exists and its signature
if hasattr(oasis, 'generate_reddit_agent_graph'):
    print('\n=== generate_reddit_agent_graph signature ===')
    print(inspect.signature(oasis.generate_reddit_agent_graph))
else:
    # Try alternate locations
    from oasis.social_agent import agents_generator
    print('\n=== agents_generator exports ===')
    print([x for x in dir(agents_generator) if 'reddit' in x.lower() or 'generate' in x.lower()])

# Check DefaultPlatformType
if hasattr(oasis, 'DefaultPlatformType'):
    print('\n=== DefaultPlatformType values ===')
    print(list(oasis.DefaultPlatformType))

# Check ActionType
from oasis import ActionType
print('\n=== Reddit actions ===')
print(ActionType.get_default_reddit_actions())

# Check LLMAction / ManualAction
from oasis import LLMAction, ManualAction
print('\n=== LLMAction signature ===')
print(inspect.signature(LLMAction))
print('\n=== ManualAction signature ===')
print(inspect.signature(ManualAction))
"
```

**Record the actual function names, signatures, and enum values.** If they differ from the code below, adapt `run_simulation.py` accordingly before proceeding to Step 1. Key things that may differ:
- `generate_reddit_agent_graph` may be in `oasis.social_agent.agents_generator` instead of `oasis`
- `profile_path` parameter may be named differently or expect a list instead of a file path
- `oasis.make()` may have different parameter names
- `LLMAction` constructor may require arguments

- [ ] **Step 1: Write the simulation runner**

Create `simulation/scripts/run_simulation.py`:

```python
"""Core simulation runner — loads agents, seeds post, runs OASIS Reddit sim."""
import asyncio
import argparse
import json
import os
import random
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Add parent to path for config import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from camel.models import ModelFactory
from camel.types import ModelPlatformType
import oasis
from oasis import ActionType, LLMAction, ManualAction

from config.simulation_config import PLATFORM_CONFIG, ACTIVITY_CONFIGS, NUM_ROUNDS


def load_profiles(profiles_path: str) -> list[dict]:
    """Load agent profiles from JSON file."""
    with open(profiles_path) as f:
        return json.load(f)


def get_archetype(username: str, profiles: list[dict]) -> str:
    """Map a profile to its archetype based on username prefix convention.

    Username convention: {archetype_prefix}_{identifier}
    E.g., 'skeptical_pm_01' -> 'skeptical_pm'
    """
    # Match against known archetype prefixes
    archetype_map = {
        "founder_early": "saas_founder_early",
        "founder_scaled": "saas_founder_scaled",
        "skeptic": "skeptical_pm",
        "indie": "indie_hacker",
        "hr": "hr_people_ops",
        "lurker": "lurker",
        "regular": "community_regular",
        "vc": "vc_growth",
    }
    for prefix, archetype in archetype_map.items():
        if prefix in username:
            return archetype
    return "saas_founder_early"  # fallback


def create_model():
    """Create MiniMax 2.7 model via CAMEL's OpenAI-compatible adapter."""
    api_key = os.getenv("MINIMAX_API_KEY")
    if not api_key:
        raise ValueError("MINIMAX_API_KEY not set in environment")

    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type="MiniMax-Text-01",
        api_key=api_key,
        url="https://api.minimax.chat/v1",
        model_config_dict={"temperature": 0.8},
    )


def load_post_content(post_path: str) -> str:
    """Load post content from a text file."""
    with open(post_path) as f:
        return f.read().strip()


def get_agent_activity(username: str, profiles: list[dict], current_round: int) -> dict | None:
    """Determine if and how an agent should act in the current round.

    Returns None if agent is inactive, or a dict with:
      - should_comment: bool (probabilistic based on comments_per_round)
      - should_vote: bool (probabilistic based on vote_probability)
    """
    archetype = get_archetype(username, profiles)
    config = ACTIVITY_CONFIGS.get(archetype)
    if not config:
        return {"should_comment": True, "should_vote": True}

    low, high = config["active_rounds"]
    if not (low <= current_round <= high):
        return None

    # Probabilistic activation based on activity_level
    if random.random() >= config["activity_level"]:
        return None

    # Determine comment behavior
    min_comments, max_comments = config["comments_per_round"]
    should_comment = random.randint(min_comments, max_comments) > 0

    # Determine vote behavior
    should_vote = random.random() < config["vote_probability"]

    return {"should_comment": should_comment, "should_vote": should_vote}


async def run_simulation(
    post_path: str,
    profiles_path: str,
    tag: str,
    results_dir: str,
):
    """Run a full Reddit simulation."""
    print(f"=== Starting simulation: {tag} ===")

    # Load inputs
    profiles = load_profiles(profiles_path)
    post_content = load_post_content(post_path)
    model = create_model()

    print(f"Loaded {len(profiles)} agent profiles")
    print(f"Post length: {len(post_content)} chars")

    # Available Reddit actions
    available_actions = ActionType.get_default_reddit_actions()

    # Generate agent graph from profiles
    agent_graph = await oasis.generate_reddit_agent_graph(
        profile_path=profiles_path,
        model=model,
        available_actions=available_actions,
    )

    # Create OASIS environment
    db_path = os.path.join(results_dir, f"{tag}.db")
    env = oasis.make(
        agent_graph=agent_graph,
        platform=oasis.DefaultPlatformType.REDDIT,
        database_path=db_path,
    )

    await env.reset()
    print(f"Environment initialized. DB: {db_path}")

    # Get the first agent to seed the post (acts as "OP")
    agents = list(env.agent_graph.get_agents())
    op_agent_id, op_agent = agents[0]

    # Seed the launch post
    seed_action = {
        op_agent: ManualAction(
            action_type=ActionType.CREATE_POST,
            action_args={"content": post_content},
        )
    }
    await env.step(seed_action)
    print(f"Post seeded by {op_agent.user_info.user_name}")

    # Run simulation rounds
    for round_num in range(1, NUM_ROUNDS + 1):
        print(f"\n--- Round {round_num}/{NUM_ROUNDS} ---")

        # Build actions for this round based on activity configs
        round_actions = {}
        active_count = 0
        for agent_id, agent in agents:
            username = agent.user_info.user_name
            activity = get_agent_activity(username, profiles, round_num)
            if activity is not None:
                # Filter available actions based on activity config
                allowed = list(ActionType.get_default_reddit_actions())
                if not activity["should_comment"]:
                    allowed = [a for a in allowed if a != ActionType.CREATE_COMMENT]
                if not activity["should_vote"]:
                    allowed = [a for a in allowed
                               if a not in (ActionType.LIKE_POST, ActionType.DISLIKE_POST,
                                            ActionType.LIKE_COMMENT, ActionType.DISLIKE_COMMENT)]
                round_actions[agent] = LLMAction()
                active_count += 1

        print(f"Active agents: {active_count}/{len(agents)}")

        if round_actions:
            await env.step(round_actions)

    print(f"\n=== Simulation complete: {tag} ===")
    print(f"Results saved to: {db_path}")

    await env.close()
    return db_path


def main():
    parser = argparse.ArgumentParser(description="Run Reddit post simulation")
    parser.add_argument("--post", required=True, help="Path to post text file")
    parser.add_argument("--tag", required=True, help="Run tag (determines output DB name)")
    parser.add_argument(
        "--profiles",
        default=os.path.join(os.path.dirname(__file__), "..", "profiles", "r_saas_community.json"),
        help="Path to agent profiles JSON",
    )
    parser.add_argument(
        "--results-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "results"),
        help="Directory for result DBs",
    )
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)

    asyncio.run(run_simulation(
        post_path=args.post,
        profiles_path=args.profiles,
        tag=args.tag,
        results_dir=args.results_dir,
    ))


if __name__ == "__main__":
    main()
```

**Note for implementer:** The `oasis.generate_reddit_agent_graph` function expects a specific JSON format. Verify the profiles JSON matches what OASIS expects by checking `oasis/social_agent/agents_generator.py`. The key fields OASIS looks for are: `username`, `realname`, `bio`, `persona`, `age`, `gender`, `mbti`, `country`. If the field names differ, add a mapping step before passing to `generate_reddit_agent_graph`.

- [ ] **Step 2: Verify the script parses arguments correctly**

```bash
cd simulation
source .venv/bin/activate
python scripts/run_simulation.py --help
```

Expected: Shows usage with `--post`, `--tag`, `--profiles`, `--results-dir` options.

- [ ] **Step 3: Commit**

```bash
git add simulation/scripts/run_simulation.py
git commit -m "feat: add core OASIS simulation runner"
```

---

## Task 6: Report Generator (`generate_report.py`)

**Files:**
- Create: `simulation/tests/test_report.py`
- Create: `simulation/scripts/generate_report.py`

- [ ] **Step 1: Write failing tests with a mock SQLite DB**

Create `simulation/tests/test_report.py`:

```python
"""Tests for generate_report.py — uses a mock SQLite DB."""
import os
import sys
import sqlite3
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from generate_report import (
    get_engagement_summary,
    get_comments,
    get_agent_actions,
    get_round_by_round,
    format_report,
)


@pytest.fixture
def mock_db():
    """Create a mock SQLite DB mimicking OASIS output schema."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create OASIS-compatible tables
    cursor.executescript("""
        CREATE TABLE user (
            user_id INTEGER PRIMARY KEY,
            user_name TEXT,
            name TEXT,
            bio TEXT,
            num_followings INTEGER DEFAULT 0,
            num_followers INTEGER DEFAULT 0
        );
        CREATE TABLE post (
            post_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            content TEXT,
            num_likes INTEGER DEFAULT 0,
            num_dislikes INTEGER DEFAULT 0,
            num_shares INTEGER DEFAULT 0,
            created_at TEXT
        );
        CREATE TABLE comment (
            comment_id INTEGER PRIMARY KEY,
            post_id INTEGER,
            user_id INTEGER,
            content TEXT,
            num_likes INTEGER DEFAULT 0,
            created_at TEXT
        );
        CREATE TABLE trace (
            trace_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            action TEXT,
            info TEXT,
            created_at TEXT
        );
        CREATE TABLE "like" (
            user_id INTEGER,
            post_id INTEGER
        );
        CREATE TABLE dislike (
            user_id INTEGER,
            post_id INTEGER
        );
    """)

    # Insert mock data: 5 users, 1 post, 4 comments
    cursor.execute("INSERT INTO user VALUES (1, 'op_user', 'OP', 'The poster', 0, 0)")
    cursor.execute("INSERT INTO user VALUES (2, 'founder_early_01', 'Alex', 'SaaS founder', 0, 0)")
    cursor.execute("INSERT INTO user VALUES (3, 'skeptic_01', 'Jordan', 'Skeptical PM', 0, 0)")
    cursor.execute("INSERT INTO user VALUES (4, 'lurker_01', 'Sam', 'Lurker', 0, 0)")
    cursor.execute("INSERT INTO user VALUES (5, 'hr_01', 'Priya', 'HR Lead', 0, 0)")

    cursor.execute(
        "INSERT INTO post VALUES (1, 1, 'Launch post content here', 3, 1, 0, '2026-03-22 10:00:00')"
    )

    cursor.execute(
        "INSERT INTO comment VALUES (1, 1, 2, 'Love this approach! 78%% completion is impressive.', 2, '2026-03-22 10:30:00')"
    )
    cursor.execute(
        "INSERT INTO comment VALUES (2, 1, 3, 'How is this different from Lattice? Pricing seems steep.', 0, '2026-03-22 11:00:00')"
    )
    cursor.execute(
        "INSERT INTO comment VALUES (3, 1, 5, 'Does it integrate with BambooHR?', 1, '2026-03-22 12:00:00')"
    )
    cursor.execute(
        "INSERT INTO comment VALUES (4, 1, 3, 'Show me real retention data, not just NPS.', 0, '2026-03-22 13:00:00')"
    )

    # Trace entries
    cursor.execute("INSERT INTO trace VALUES (1, 2, 'like_post', '{\"post_id\": 1}', '2026-03-22 10:30:00')")
    cursor.execute("INSERT INTO trace VALUES (2, 3, 'create_comment', '{\"post_id\": 1}', '2026-03-22 11:00:00')")
    cursor.execute("INSERT INTO trace VALUES (3, 4, 'like_post', '{\"post_id\": 1}', '2026-03-22 14:00:00')")
    cursor.execute("INSERT INTO trace VALUES (4, 5, 'create_comment', '{\"post_id\": 1}', '2026-03-22 12:00:00')")

    conn.commit()
    conn.close()

    yield db_path
    os.unlink(db_path)


def test_engagement_summary(mock_db):
    summary = get_engagement_summary(mock_db)
    assert summary["score"] == 2  # 3 likes - 1 dislike
    assert summary["num_likes"] == 3
    assert summary["num_dislikes"] == 1
    assert summary["comment_count"] == 4
    assert summary["total_agents"] == 5
    # engagement_rate = agents who acted / total agents
    assert summary["engagement_rate"] > 0


def test_get_comments(mock_db):
    comments = get_comments(mock_db)
    assert len(comments) == 4
    assert any("Lattice" in c["content"] for c in comments)


def test_get_agent_actions(mock_db):
    actions = get_agent_actions(mock_db)
    assert len(actions) > 0
    # Check that actions have required fields
    for action in actions:
        assert "username" in action
        assert "action" in action


def test_format_report_contains_sections(mock_db):
    # Use mock data without LLM calls (pass skip_llm=True)
    report = format_report(mock_db, skip_llm=True)
    assert "ENGAGEMENT SUMMARY" in report
    assert "AGENT-BY-AGENT REACTIONS" in report
    assert "ACTIONABLE INSIGHTS" in report
    assert "Score:" in report
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd simulation
source .venv/bin/activate
python -m pytest tests/test_report.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the report generator**

Create `simulation/scripts/generate_report.py`:

```python
"""Generate a detailed report from a single simulation run's SQLite DB."""
import argparse
import json
import os
import sqlite3
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def get_engagement_summary(db_path: str) -> dict:
    """Extract engagement metrics from the simulation DB."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Post metrics (assume post_id=1 is the seeded post)
    cursor.execute(
        "SELECT num_likes, num_dislikes FROM post WHERE post_id = 1"
    )
    row = cursor.fetchone()
    num_likes = row[0] if row else 0
    num_dislikes = row[1] if row else 0

    # Comment count
    cursor.execute("SELECT COUNT(*) FROM comment WHERE post_id = 1")
    comment_count = cursor.fetchone()[0]

    # Total agents
    cursor.execute("SELECT COUNT(*) FROM user")
    total_agents = cursor.fetchone()[0]

    # Agents who took any action
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM trace")
    active_agents = cursor.fetchone()[0]

    conn.close()

    engagement_rate = active_agents / total_agents if total_agents > 0 else 0

    return {
        "score": num_likes - num_dislikes,
        "num_likes": num_likes,
        "num_dislikes": num_dislikes,
        "comment_count": comment_count,
        "total_agents": total_agents,
        "active_agents": active_agents,
        "engagement_rate": round(engagement_rate * 100, 1),
    }


def get_comments(db_path: str) -> list[dict]:
    """Get all comments on the seeded post."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.comment_id, c.content, c.num_likes, c.created_at,
               u.user_name, u.name
        FROM comment c
        JOIN user u ON c.user_id = u.user_id
        WHERE c.post_id = 1
        ORDER BY c.created_at
    """)
    comments = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return comments


def get_agent_actions(db_path: str) -> list[dict]:
    """Get per-agent action summary."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.user_name as username, t.action, t.info, t.created_at
        FROM trace t
        JOIN user u ON t.user_id = u.user_id
        ORDER BY t.created_at
    """)
    actions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return actions


def get_round_by_round(db_path: str, num_rounds: int = 10) -> list[dict]:
    """Get engagement metrics grouped by simulated round.

    Since OASIS doesn't tag rounds explicitly, we divide the trace
    timeline into num_rounds equal buckets.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT MIN(created_at), MAX(created_at) FROM trace")
    row = cursor.fetchone()
    if not row or not row[0]:
        conn.close()
        return []

    # Get all traces ordered by time
    cursor.execute("""
        SELECT action, created_at FROM trace ORDER BY created_at
    """)
    traces = cursor.fetchall()
    conn.close()

    if not traces:
        return []

    # Divide into equal buckets
    bucket_size = max(1, len(traces) // num_rounds)
    rounds = []
    for i in range(num_rounds):
        start = i * bucket_size
        end = start + bucket_size if i < num_rounds - 1 else len(traces)
        bucket = traces[start:end]

        likes = sum(1 for t in bucket if "like" in t[0].lower() and "dislike" not in t[0].lower())
        dislikes = sum(1 for t in bucket if "dislike" in t[0].lower())
        comments = sum(1 for t in bucket if "comment" in t[0].lower())

        rounds.append({
            "round": i + 1,
            "actions": len(bucket),
            "likes": likes,
            "dislikes": dislikes,
            "comments": comments,
            "score_delta": likes - dislikes,
        })

    return rounds


def classify_sentiment_llm(comments: list[dict]) -> list[dict]:
    """Classify comment sentiment using LLM. Returns comments with 'sentiment' field added."""
    if not comments:
        return comments

    from camel.models import ModelFactory
    from camel.types import ModelPlatformType
    from camel.agents import ChatAgent
    from camel.messages import BaseMessage

    model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type="MiniMax-Text-01",
        api_key=os.getenv("MINIMAX_API_KEY"),
        url="https://api.minimax.chat/v1",
        model_config_dict={"temperature": 0.0},
    )

    comments_text = "\n".join(
        f"{i+1}. [{c['user_name']}]: {c['content']}"
        for i, c in enumerate(comments)
    )

    prompt = f"""Classify each comment as exactly one of: supportive, neutral, skeptical.

Comments:
{comments_text}

Respond with ONLY a JSON array of objects: [{{"index": 1, "sentiment": "supportive"}}, ...]
No other text."""

    agent = ChatAgent(model=model, system_message="You classify comment sentiment.")
    response = agent.step(BaseMessage.make_user_message(role_name="user", content=prompt))

    try:
        sentiments = json.loads(response.msg.content)
        for s in sentiments:
            idx = s["index"] - 1
            if 0 <= idx < len(comments):
                comments[idx]["sentiment"] = s["sentiment"]
    except (json.JSONDecodeError, KeyError):
        # Fallback: mark all as neutral
        for c in comments:
            c.setdefault("sentiment", "neutral")

    return comments


def extract_themes_llm(comments: list[dict]) -> list[str]:
    """Extract top recurring themes from comments using LLM."""
    if not comments:
        return []

    from camel.models import ModelFactory
    from camel.types import ModelPlatformType
    from camel.agents import ChatAgent
    from camel.messages import BaseMessage

    model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type="MiniMax-Text-01",
        api_key=os.getenv("MINIMAX_API_KEY"),
        url="https://api.minimax.chat/v1",
        model_config_dict={"temperature": 0.0},
    )

    comments_text = "\n".join(f"- {c['content']}" for c in comments)

    prompt = f"""Given these Reddit comments on a SaaS launch post, identify the top 5 recurring themes.

Comments:
{comments_text}

Respond with ONLY a JSON array of strings: ["theme 1 (N mentions)", "theme 2 (N mentions)", ...]
No other text."""

    agent = ChatAgent(model=model, system_message="You extract discussion themes.")
    response = agent.step(BaseMessage.make_user_message(role_name="user", content=prompt))

    try:
        return json.loads(response.msg.content)
    except json.JSONDecodeError:
        return ["Could not extract themes"]


def generate_insights_llm(comments: list[dict], summary: dict, themes: list[str]) -> list[str]:
    """Generate actionable recommendations based on simulation data."""
    if not comments:
        return []

    from camel.models import ModelFactory
    from camel.types import ModelPlatformType
    from camel.agents import ChatAgent
    from camel.messages import BaseMessage

    model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type="MiniMax-Text-01",
        api_key=os.getenv("MINIMAX_API_KEY"),
        url="https://api.minimax.chat/v1",
        model_config_dict={"temperature": 0.3},
    )

    sentiment_counts = {}
    for c in comments:
        s = c.get("sentiment", "unknown")
        sentiment_counts[s] = sentiment_counts.get(s, 0) + 1

    comments_text = "\n".join(f"- [{c.get('sentiment', '?')}] {c['content']}" for c in comments)

    prompt = f"""Based on this simulated Reddit community reaction to a SaaS launch post, provide 3-5 specific, actionable recommendations for improving the post.

Score: +{summary['score']} ({summary['num_likes']} upvotes, {summary['num_dislikes']} downvotes)
Comments: {summary['comment_count']}
Sentiment: {sentiment_counts}
Top themes: {themes}

Comments:
{comments_text}

Respond with ONLY a JSON array of strings, each a concise actionable recommendation.
No other text."""

    agent = ChatAgent(model=model, system_message="You provide actionable content recommendations.")
    response = agent.step(BaseMessage.make_user_message(role_name="user", content=prompt))

    try:
        return json.loads(response.msg.content)
    except json.JSONDecodeError:
        return ["Could not generate insights"]


def format_report(db_path: str, skip_llm: bool = False) -> str:
    """Generate formatted report string from simulation DB."""
    summary = get_engagement_summary(db_path)
    comments = get_comments(db_path)
    actions = get_agent_actions(db_path)
    rounds = get_round_by_round(db_path)

    # Sentiment and themes (LLM-powered unless skipped)
    if not skip_llm and comments:
        comments = classify_sentiment_llm(comments)
        themes = extract_themes_llm(comments)
    else:
        for c in comments:
            c["sentiment"] = "unknown"
        themes = ["(LLM analysis skipped)"]

    # Build report
    lines = []
    tag = os.path.splitext(os.path.basename(db_path))[0]

    lines.append("=" * 55)
    lines.append(f"  SIMULATION REPORT: {tag}")
    lines.append(f"  Agents: {summary['total_agents']} | Rounds: 10")
    lines.append("=" * 55)

    # Engagement summary
    lines.append("\nENGAGEMENT SUMMARY")
    lines.append(f"  Score:           +{summary['score']} ({summary['num_likes']} upvotes, {summary['num_dislikes']} downvotes)")
    lines.append(f"  Comments:        {summary['comment_count']}")
    lines.append(f"  Engagement rate: {summary['engagement_rate']}% ({summary['active_agents']}/{summary['total_agents']} agents)")

    # Sentiment breakdown
    if comments:
        sentiment_counts = {"supportive": 0, "neutral": 0, "skeptical": 0, "unknown": 0}
        for c in comments:
            s = c.get("sentiment", "unknown")
            sentiment_counts[s] = sentiment_counts.get(s, 0) + 1

        total = len(comments)
        lines.append("\nSENTIMENT BREAKDOWN")
        for sentiment in ["supportive", "neutral", "skeptical"]:
            count = sentiment_counts[sentiment]
            pct = round(count / total * 100) if total > 0 else 0
            lines.append(f"  {sentiment.capitalize():12s} {count} comments ({pct}%)")

    # Top themes
    lines.append("\nTOP THEMES IN COMMENTS")
    for i, theme in enumerate(themes, 1):
        lines.append(f"  {i}. {theme}")

    # Agent-by-agent reactions
    lines.append("\nAGENT-BY-AGENT REACTIONS")
    lines.append(f"  {'Agent':<22s} {'Action':<10s} {'Comment (truncated)':<40s}")
    lines.append(f"  {'-'*22} {'-'*10} {'-'*40}")

    # Group actions by agent
    agent_summary = {}
    for a in actions:
        username = a["username"]
        if username not in agent_summary:
            agent_summary[username] = {"actions": [], "comment": ""}
        agent_summary[username]["actions"].append(a["action"])

    for c in comments:
        username = c["user_name"]
        if username in agent_summary:
            agent_summary[username]["comment"] = c["content"][:40]

    for username, data in agent_summary.items():
        action_str = ", ".join(set(data["actions"]))[:10]
        comment_str = data["comment"] or "-"
        lines.append(f"  {username:<22s} {action_str:<10s} {comment_str:<40s}")

    # Round-by-round
    if rounds:
        lines.append("\nROUND-BY-ROUND ENGAGEMENT")
        cumulative_score = 0
        for r in rounds:
            cumulative_score += r["score_delta"]
            bar_len = min(r["actions"], 20)
            bar = "#" * bar_len + "." * (20 - bar_len)
            lines.append(
                f"  R{r['round']:<2d}: [{bar}]  "
                f"+{cumulative_score} score, {r['comments']} comments"
            )

    # Actionable Insights (LLM-powered)
    if not skip_llm and comments:
        insights = generate_insights_llm(comments, summary, themes)
        lines.append("\nACTIONABLE INSIGHTS")
        for insight in insights:
            lines.append(f"  - {insight}")
    elif not skip_llm:
        lines.append("\nACTIONABLE INSIGHTS")
        lines.append("  (No comments to analyze)")
    else:
        lines.append("\nACTIONABLE INSIGHTS")
        lines.append("  (LLM analysis skipped)")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate report from simulation DB")
    parser.add_argument("db", help="Path to simulation SQLite DB")
    parser.add_argument("--output", help="Output file path (default: stdout)")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM-powered analysis")
    args = parser.parse_args()

    report = format_report(args.db, skip_llm=args.skip_llm)

    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report written to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd simulation
source .venv/bin/activate
python -m pytest tests/test_report.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add simulation/scripts/generate_report.py simulation/tests/test_report.py
git commit -m "feat: add report generator with engagement, sentiment, and per-agent analysis"
```

---

## Task 7: Comparison Script (`compare_runs.py`)

**Files:**
- Create: `simulation/tests/test_compare.py`
- Create: `simulation/scripts/compare_runs.py`

- [ ] **Step 1: Write the failing test**

Create `simulation/tests/test_compare.py`:

```python
"""Tests for compare_runs.py — uses mock SQLite DBs."""
import os
import sys
import sqlite3
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from compare_runs import load_run_metrics, determine_winner, format_comparison


def _create_mock_db(num_likes, num_dislikes, num_comments):
    """Create a minimal mock DB with specified metrics."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE user (user_id INTEGER PRIMARY KEY, user_name TEXT, name TEXT, bio TEXT, num_followings INTEGER DEFAULT 0, num_followers INTEGER DEFAULT 0);
        CREATE TABLE post (post_id INTEGER PRIMARY KEY, user_id INTEGER, content TEXT, num_likes INTEGER DEFAULT 0, num_dislikes INTEGER DEFAULT 0, num_shares INTEGER DEFAULT 0, created_at TEXT);
        CREATE TABLE comment (comment_id INTEGER PRIMARY KEY, post_id INTEGER, user_id INTEGER, content TEXT, num_likes INTEGER DEFAULT 0, created_at TEXT);
        CREATE TABLE trace (trace_id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT, info TEXT, created_at TEXT);
    """)

    cursor.execute(
        "INSERT INTO user VALUES (1, 'op', 'OP', 'bio', 0, 0)"
    )
    cursor.execute(
        f"INSERT INTO post VALUES (1, 1, 'content', {num_likes}, {num_dislikes}, 0, '2026-01-01')"
    )
    for i in range(num_comments):
        cursor.execute(
            f"INSERT INTO comment VALUES ({i+1}, 1, 1, 'comment {i}', 0, '2026-01-01')"
        )

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def mock_dbs():
    paths = [
        _create_mock_db(num_likes=10, num_dislikes=2, num_comments=8),   # score 8
        _create_mock_db(num_likes=15, num_dislikes=3, num_comments=5),   # score 12 (winner)
        _create_mock_db(num_likes=7, num_dislikes=1, num_comments=12),   # score 6
    ]
    yield paths
    for p in paths:
        os.unlink(p)


def test_load_run_metrics(mock_dbs):
    metrics = load_run_metrics(mock_dbs[0])
    assert metrics["score"] == 8
    assert metrics["num_likes"] == 10
    assert metrics["comment_count"] == 8


def test_determine_winner(mock_dbs):
    all_metrics = [
        {"tag": "v1", **load_run_metrics(mock_dbs[0])},
        {"tag": "v2", **load_run_metrics(mock_dbs[1])},
        {"tag": "v3", **load_run_metrics(mock_dbs[2])},
    ]
    winner = determine_winner(all_metrics)
    assert winner["tag"] == "v2"  # highest score = 12


def test_format_comparison(mock_dbs):
    all_metrics = [
        {"tag": "v1", **load_run_metrics(mock_dbs[0])},
        {"tag": "v2", **load_run_metrics(mock_dbs[1])},
        {"tag": "v3", **load_run_metrics(mock_dbs[2])},
    ]
    output = format_comparison(all_metrics)
    assert "v1" in output
    assert "v2" in output
    assert "v3" in output
    assert "WINNER" in output or "winner" in output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd simulation
source .venv/bin/activate
python -m pytest tests/test_compare.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the comparison script**

Create `simulation/scripts/compare_runs.py`:

```python
"""Compare multiple simulation runs side-by-side."""
import argparse
import json
import os
import sqlite3
import sys


def load_run_metrics(db_path: str) -> dict:
    """Load key metrics from a simulation DB."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Post score
    cursor.execute("SELECT num_likes, num_dislikes FROM post WHERE post_id = 1")
    row = cursor.fetchone()
    num_likes = row[0] if row else 0
    num_dislikes = row[1] if row else 0

    # Comment count
    cursor.execute("SELECT COUNT(*) FROM comment WHERE post_id = 1")
    comment_count = cursor.fetchone()[0]

    # Total agents and active agents
    cursor.execute("SELECT COUNT(*) FROM user")
    total_agents = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM trace")
    active_agents = cursor.fetchone()[0]

    conn.close()

    engagement_rate = round(active_agents / total_agents * 100, 1) if total_agents > 0 else 0

    return {
        "score": num_likes - num_dislikes,
        "num_likes": num_likes,
        "num_dislikes": num_dislikes,
        "comment_count": comment_count,
        "total_agents": total_agents,
        "active_agents": active_agents,
        "engagement_rate": engagement_rate,
    }


def get_sentiment_distribution(db_path: str) -> dict:
    """Classify comments and return sentiment percentages.

    Uses LLM to classify each comment. Returns dict with
    supportive_pct, neutral_pct, skeptical_pct.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.content, u.user_name
        FROM comment c JOIN user u ON c.user_id = u.user_id
        WHERE c.post_id = 1
    """)
    comments = [dict(row) for row in cursor.fetchall()]
    conn.close()

    if not comments:
        return {"supportive_pct": 0, "neutral_pct": 0, "skeptical_pct": 0}

    try:
        from camel.models import ModelFactory
        from camel.types import ModelPlatformType
        from camel.agents import ChatAgent
        from camel.messages import BaseMessage

        model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type="MiniMax-Text-01",
            api_key=os.getenv("MINIMAX_API_KEY"),
            url="https://api.minimax.chat/v1",
            model_config_dict={"temperature": 0.0},
        )

        comments_text = "\n".join(
            f"{i+1}. [{c['user_name']}]: {c['content']}"
            for i, c in enumerate(comments)
        )

        prompt = f"""Classify each comment as exactly one of: supportive, neutral, skeptical.

Comments:
{comments_text}

Respond with ONLY a JSON array: [{{"index": 1, "sentiment": "supportive"}}, ...]"""

        agent = ChatAgent(model=model, system_message="You classify sentiment.")
        response = agent.step(BaseMessage.make_user_message(role_name="user", content=prompt))

        sentiments = json.loads(response.msg.content)
        counts = {"supportive": 0, "neutral": 0, "skeptical": 0}
        for s in sentiments:
            sent = s.get("sentiment", "neutral")
            counts[sent] = counts.get(sent, 0) + 1

        total = len(comments)
        return {
            "supportive_pct": round(counts["supportive"] / total * 100, 1),
            "neutral_pct": round(counts["neutral"] / total * 100, 1),
            "skeptical_pct": round(counts["skeptical"] / total * 100, 1),
        }
    except Exception:
        return {"supportive_pct": 0, "neutral_pct": 0, "skeptical_pct": 0}


def get_key_themes(db_path: str) -> list[str]:
    """Extract top themes from comments using LLM."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT content FROM comment WHERE post_id = 1")
    comments = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not comments:
        return []

    try:
        from camel.models import ModelFactory
        from camel.types import ModelPlatformType
        from camel.agents import ChatAgent
        from camel.messages import BaseMessage

        model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type="MiniMax-Text-01",
            api_key=os.getenv("MINIMAX_API_KEY"),
            url="https://api.minimax.chat/v1",
            model_config_dict={"temperature": 0.0},
        )

        comments_text = "\n".join(f"- {c}" for c in comments)
        prompt = f"""Top 3 recurring themes in these comments on a SaaS launch post:

{comments_text}

Respond with ONLY a JSON array of short strings: ["theme1", "theme2", "theme3"]"""

        agent = ChatAgent(model=model, system_message="You extract themes.")
        response = agent.step(BaseMessage.make_user_message(role_name="user", content=prompt))
        return json.loads(response.msg.content)
    except Exception:
        return []


def determine_winner(all_metrics: list[dict]) -> dict:
    """Determine winner by highest final score.

    Per spec: highest score (upvotes - downvotes). Ties broken by highest
    supportive comment percentage.
    """
    sorted_metrics = sorted(
        all_metrics,
        key=lambda m: (m["score"], m.get("supportive_pct", 0)),
        reverse=True,
    )
    return sorted_metrics[0]


def format_comparison(all_metrics: list[dict]) -> str:
    """Format side-by-side comparison table."""
    winner = determine_winner(all_metrics)

    lines = []
    lines.append("=" * 70)
    lines.append(f"  A/B COMPARISON: {len(all_metrics)} variants")
    lines.append("=" * 70)
    lines.append("")

    # Header row
    col_width = 18
    header = f"  {'Metric':<20s}"
    for m in all_metrics:
        tag = m["tag"]
        marker = " *" if m["tag"] == winner["tag"] else ""
        header += f"| {tag + marker:>{col_width}s} "
    lines.append(header)
    lines.append("  " + "-" * 20 + ("+" + "-" * (col_width + 1)) * len(all_metrics))

    # Data rows
    metrics_to_show = [
        ("Final Score", "score"),
        ("Upvotes", "num_likes"),
        ("Downvotes", "num_dislikes"),
        ("Comments", "comment_count"),
        ("Engagement Rate", "engagement_rate"),
        ("Supportive %", "supportive_pct"),
        ("Neutral %", "neutral_pct"),
        ("Skeptical %", "skeptical_pct"),
    ]

    for label, key in metrics_to_show:
        row = f"  {label:<20s}"
        for m in all_metrics:
            val = m.get(key, "-")
            if key in ("engagement_rate", "supportive_pct", "neutral_pct", "skeptical_pct"):
                val_str = f"{val}%" if val != "-" else "-"
            elif key == "score":
                val_str = f"+{val}" if isinstance(val, (int, float)) and val >= 0 else str(val)
            else:
                val_str = str(val)
            row += f"| {val_str:>{col_width}s} "
        lines.append(row)

    lines.append("  " + "-" * 20 + ("+" + "-" * (col_width + 1)) * len(all_metrics))

    # Key themes per variant
    any_has_themes = any(m.get("themes") for m in all_metrics)
    if any_has_themes:
        lines.append("")
        lines.append("KEY THEMES PER VARIANT")
        for m in all_metrics:
            themes = m.get("themes", [])
            lines.append(f"  {m['tag']}: {', '.join(themes) if themes else '(none)'}")

    # Winner
    lines.append("")
    lines.append(f"  WINNER: {winner['tag']} (score: +{winner['score']})")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Compare multiple simulation runs")
    parser.add_argument("dbs", nargs="+", help="Paths to simulation SQLite DBs")
    parser.add_argument("--output", help="Output file path (default: stdout)")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM-powered sentiment/themes")
    args = parser.parse_args()

    all_metrics = []
    for db_path in args.dbs:
        tag = os.path.splitext(os.path.basename(db_path))[0]
        metrics = load_run_metrics(db_path)
        metrics["tag"] = tag

        # Add sentiment and theme analysis per variant
        if not args.skip_llm:
            sentiment = get_sentiment_distribution(db_path)
            metrics.update(sentiment)
            metrics["themes"] = get_key_themes(db_path)
        else:
            metrics["supportive_pct"] = "-"
            metrics["neutral_pct"] = "-"
            metrics["skeptical_pct"] = "-"
            metrics["themes"] = []

        all_metrics.append(metrics)

    output = format_comparison(all_metrics)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Comparison written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd simulation
source .venv/bin/activate
python -m pytest tests/test_compare.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add simulation/scripts/compare_runs.py simulation/tests/test_compare.py
git commit -m "feat: add multi-run comparison script with winner designation"
```

---

## Task 8: Post Variants

**Files:**
- Create: `simulation/posts/original.txt`
- Create: `simulation/posts/variant_punchy_title.txt`
- Create: `simulation/posts/variant_lower_pricing.txt`

- [ ] **Step 1: Parse post.md into original.txt**

```bash
cd simulation
source .venv/bin/activate
python scripts/parse_post.py ../post.md --output posts/original.txt
```

Expected: `posts/original.txt` created with plain-text version of the post.

- [ ] **Step 2: Verify original.txt looks correct**

```bash
head -20 simulation/posts/original.txt
```

Expected: Title on first line, body below. No markdown artifacts.

- [ ] **Step 3: Create variant_punchy_title.txt**

Copy `original.txt` to `variant_punchy_title.txt`. Change only the title to something shorter and hookier:

Original: `"We built a tool that predicts employee burnout before it turns into a resignation. Here's what we learned from 14 beta companies."`

Variant: `"After-hours commits predict resignations 3-5 weeks early. We built a tool around it."`

Keep the body identical.

- [ ] **Step 4: Create variant_lower_pricing.txt**

Copy `original.txt` to `variant_lower_pricing.txt`. Change only the pricing section:

- Starter: $4/user/mo → $2/user/mo
- Growth: $8/user/mo → $5/user/mo
- Keep "20% off annual"

Keep everything else identical.

- [ ] **Step 5: Commit**

```bash
git add simulation/posts/
git commit -m "feat: add original post and two A/B variants"
```

---

## Task 9: README

**Files:**
- Create: `simulation/README.md`

- [ ] **Step 1: Write the README**

Create `simulation/README.md` covering:

1. **What this is** — one paragraph explaining the Reddit simulation
2. **Prerequisites** — Python 3.11+, MiniMax API key
3. **Setup** — venv, pip install, .env
4. **Usage** — exact commands for:
   - Running a single simulation: `python scripts/run_simulation.py --post posts/original.txt --tag "v1-original"`
   - Generating a report: `python scripts/generate_report.py results/v1-original.db`
   - Comparing runs: `python scripts/compare_runs.py results/v1-original.db results/v2-punchy-title.db results/v3-lower-pricing.db`
5. **Running tests** — `python -m pytest tests/ -v`
6. **Creating new variants** — how to add post variants
7. **Customizing agents** — how to edit profiles

- [ ] **Step 2: Commit**

```bash
git add simulation/README.md
git commit -m "docs: add simulation README with setup and usage instructions"
```

---

## Task 10: End-to-End Smoke Test

**No new files.** This validates the full pipeline works.

- [ ] **Step 1: Run all unit tests**

```bash
cd simulation
source .venv/bin/activate
python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 2: Run a simulation with the original post**

```bash
cd simulation
source .venv/bin/activate
python scripts/run_simulation.py --post posts/original.txt --tag "smoke-test"
```

Expected: Completes 10 rounds, prints progress per round, writes `results/smoke-test.db`.

**If this fails due to OASIS API differences:** Check `oasis.generate_reddit_agent_graph` — the function signature may differ from what the librarian reported. Adapt `run_simulation.py` accordingly. Key things to check:
- Does `generate_reddit_agent_graph` exist, or is the function named differently?
- Does it accept `profile_path` as a string, or does it need a loaded list?
- Does `oasis.make()` accept `platform` as a `DefaultPlatformType` enum?

- [ ] **Step 3: Generate a report from the smoke test**

```bash
python scripts/generate_report.py results/smoke-test.db --skip-llm
```

Expected: Prints formatted report with engagement summary, agent reactions, round-by-round. (Sentiment shows "unknown" since `--skip-llm`.)

- [ ] **Step 4: Generate a report WITH LLM analysis**

```bash
python scripts/generate_report.py results/smoke-test.db
```

Expected: Same report but with real sentiment classification and theme extraction.

- [ ] **Step 5: Run all three variants and compare**

```bash
python scripts/run_simulation.py --post posts/original.txt --tag "v1-original"
python scripts/run_simulation.py --post posts/variant_punchy_title.txt --tag "v2-punchy-title"
python scripts/run_simulation.py --post posts/variant_lower_pricing.txt --tag "v3-lower-pricing"
python scripts/compare_runs.py results/v1-original.db results/v2-punchy-title.db results/v3-lower-pricing.db
```

Expected: Comparison table printed with all three variants, metrics, and a winner.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "chore: complete reddit simulation pipeline — all tests passing"
```
