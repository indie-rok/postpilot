# Humanizer Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove AI writing patterns from all generated text — agent comments via batch post-processing, suggest-post and rewrite via system prompt injection.

**Architecture:** New `prompts/humanizer.py` holds the full 25-category ruleset and a batch-rewrite prompt template. `run_simulation.py` gets a `humanize_comments()` function called after `env.close()` to rewrite OASIS comments before extraction. `suggest.py` and `rewrite.py` system messages get the rules appended.

**Tech Stack:** Python, CAMEL-AI ChatAgent, SQLite, pytest

**Spec:** `docs/superpowers/specs/2026-03-24-humanizer-integration-design.md`

---

### Task 1: Create `prompts/humanizer.py` — WRITING_RULES constant

**Files:**
- Create: `simulation/prompts/humanizer.py`
- Test: `simulation/tests/test_humanizer.py`

- [ ] **Step 1: Write the test for WRITING_RULES**

```python
# simulation/tests/test_humanizer.py
# pyright: reportMissingImports=false, reportImplicitRelativeImport=false

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_writing_rules_is_nonempty_string():
    from prompts.humanizer import WRITING_RULES

    assert isinstance(WRITING_RULES, str)
    assert len(WRITING_RULES) > 1000  # full 25 categories should be substantial


def test_writing_rules_contains_all_25_categories():
    from prompts.humanizer import WRITING_RULES

    # Spot-check key categories are present
    assert "significance" in WRITING_RULES.lower() or "legacy" in WRITING_RULES.lower()
    assert "em dash" in WRITING_RULES.lower() or "em-dash" in WRITING_RULES.lower()
    assert "delve" in WRITING_RULES.lower()
    assert "rule of three" in WRITING_RULES.lower()
    assert "sycophantic" in WRITING_RULES.lower() or "servile" in WRITING_RULES.lower()
    assert "filler" in WRITING_RULES.lower()
    assert "hedging" in WRITING_RULES.lower()
    assert "parallelism" in WRITING_RULES.lower()
    assert "boldface" in WRITING_RULES.lower() or "bold" in WRITING_RULES.lower()


def test_writing_rules_contains_personality_section():
    from prompts.humanizer import WRITING_RULES

    assert "vary" in WRITING_RULES.lower()
    assert "opinion" in WRITING_RULES.lower() or "personality" in WRITING_RULES.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd simulation && python -m pytest tests/test_humanizer.py -v`
Expected: FAIL — `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Create `prompts/humanizer.py` with WRITING_RULES**

Create `simulation/prompts/humanizer.py`. This is an editorial/content task. The `WRITING_RULES` constant must contain all 25 categories from the [humanizer SKILL.md](https://github.com/blader/humanizer/blob/main/SKILL.md), adapted into prompt instruction format.

**How to generate:** Fetch the source, then transform each of the 25 categories plus the "Personality and Soul" section:

```bash
curl -sL https://raw.githubusercontent.com/blader/humanizer/main/SKILL.md
```

**Format for each category:** rule name as instruction, words-to-watch list, one BAD/GOOD example pair.

**Acceptance criteria:** The tests in Step 1 must pass — spot-checking that key terms from multiple categories are present and the string exceeds 1000 chars.

**Complete WRITING_RULES content (all 25 categories):**

```python
WRITING_RULES = """# Writing Style Rules

Write like a real person. Vary sentence rhythm -- short punchy, then longer.
Have opinions. Acknowledge complexity and mixed feelings.
Use first person when it fits. Be specific, not generic.
Let some mess in. Perfect structure feels algorithmic.

## 1. Do not inflate significance or legacy
NEVER use: stands as, is a testament, vital/significant/crucial/pivotal role/moment, underscores/highlights importance, reflects broader, evolving landscape, indelible mark, setting the stage, deeply rooted
BAD: "This initiative marks a pivotal moment in the evolution of regional statistics."
GOOD: "The institute was established in 1989 to collect regional statistics."

## 2. Do not overemphasize notability or media coverage
NEVER use: independent coverage, active social media presence, leading expert, widely recognized
BAD: "Her views have been cited in The New York Times, BBC, and Financial Times. She maintains an active social media presence."
GOOD: "In a 2024 New York Times interview, she argued that AI regulation should focus on outcomes rather than methods."

## 3. Do not use superficial -ing analyses
NEVER use: highlighting, underscoring, emphasizing, ensuring, reflecting, symbolizing, contributing to, cultivating, fostering, encompassing, showcasing
BAD: "The color palette resonates with the region's beauty, symbolizing bluebonnets, reflecting the community's connection to the land."
GOOD: "The architect chose blue, green, and gold to reference local bluebonnets and the Gulf coast."

## 4. Do not use promotional or advertisement language
NEVER use: boasts, vibrant, rich (figurative), profound, nestled, in the heart of, groundbreaking (figurative), renowned, breathtaking, must-visit, stunning, showcasing, commitment to
BAD: "Nestled within the breathtaking region, the town stands as a vibrant place with rich cultural heritage."
GOOD: "Alamata is a town in the Gonder region, known for its weekly market and 18th-century church."

## 5. Do not use vague attributions or weasel words
NEVER use: Industry reports, Observers have cited, Experts argue, Some critics argue, several sources
BAD: "Experts believe it plays a crucial role in the regional ecosystem."
GOOD: "The river supports several endemic fish species, according to a 2019 survey by the Chinese Academy of Sciences."

## 6. Do not use formulaic challenges-and-prospects sections
NEVER use: Despite its... faces challenges, Despite these challenges, Future Outlook, continues to thrive
BAD: "Despite challenges typical of urban areas, with its strategic location, the town continues to thrive."
GOOD: "Traffic congestion increased after 2015 when three new IT parks opened."

## 7. Do not use overused AI vocabulary
NEVER use: Additionally, align with, crucial, delve, emphasizing, enduring, enhance, fostering, garner, highlight (verb), interplay, intricate/intricacies, key (adjective), landscape (abstract), pivotal, showcase, tapestry (abstract), testament, underscore (verb), valuable, vibrant
BAD: "Additionally, the intricate interplay between these forces showcases a vibrant tapestry."
GOOD: "These forces interact in ways that aren't always predictable."

## 8. Do not avoid simple "is"/"are"/"has" constructions
NEVER use: serves as, stands as, marks, represents (as copula substitutes), boasts, features, offers (when "has" works)
BAD: "Gallery 825 serves as the exhibition space. The gallery features four rooms and boasts 3,000 square feet."
GOOD: "Gallery 825 is the exhibition space. It has four rooms totaling 3,000 square feet."

## 9. Do not use negative parallelisms
NEVER use: Not only...but also, It's not just X -- it's Y, It's not merely X, it's Y
BAD: "It's not just about the beat; it's part of the aggression. It's not merely a song, it's a statement."
GOOD: "The heavy beat adds to the aggressive tone."

## 10. Do not force ideas into groups of three
Avoid the "rule of three" pattern where ideas are artificially grouped into triads.
BAD: "The event features keynote sessions, panel discussions, and networking opportunities. Attendees can expect innovation, inspiration, and industry insights."
GOOD: "The event includes talks and panels. There's also time for informal networking between sessions."

## 11. Do not cycle through synonyms for the same thing
Avoid elegant variation / synonym cycling where the same noun gets different labels in consecutive sentences.
BAD: "The protagonist faces challenges. The main character must overcome obstacles. The central figure triumphs. The hero returns."
GOOD: "The protagonist faces many challenges but eventually triumphs and returns home."

## 12. Do not use false ranges
Avoid "from X to Y" constructions where X and Y aren't on a meaningful scale.
BAD: "Our journey has taken us from the singularity of the Big Bang to the grand cosmic web, from the birth of stars to the dance of dark matter."
GOOD: "The book covers the Big Bang, star formation, and current theories about dark matter."

## 13. Do not overuse em dashes
Replace em dashes (--) with commas, periods, or parentheses. Use sparingly if at all.
BAD: "The term is promoted by Dutch institutions--not by the people themselves. You don't say that--yet this continues--even in official documents."
GOOD: "The term is promoted by Dutch institutions, not by the people themselves."

## 14. Do not overuse boldface for emphasis
Remove mechanical bold emphasis. Use bold only for genuine UI labels or critical warnings.
BAD: "It blends **OKRs**, **KPIs**, and tools such as the **Business Model Canvas**."
GOOD: "It blends OKRs, KPIs, and visual strategy tools like the Business Model Canvas."

## 15. Do not use inline-header vertical lists
Avoid bullet points where each item starts with a bolded header followed by a colon.
BAD: "- **User Experience:** The UX has been improved.\\n- **Performance:** Performance has been enhanced."
GOOD: "The update improves the interface, speeds up load times, and adds end-to-end encryption."

## 16. Do not use Title Case in headings
Use sentence case for headings (capitalize only the first word).
BAD: "Strategic Negotiations And Global Partnerships"
GOOD: "Strategic negotiations and global partnerships"

## 17. Do not use emojis to decorate text
No emojis in headings, bullet points, or body text.

## 18. Use straight quotation marks, not curly quotes

## 19. Do not include collaborative communication artifacts
NEVER use: I hope this helps, Of course!, Certainly!, You're absolutely right!, Would you like..., let me know, here is a...
BAD: "Here is an overview of the French Revolution. I hope this helps! Let me know if you'd like me to expand."
GOOD: "The French Revolution began in 1789 when financial crisis and food shortages led to widespread unrest."

## 20. Do not include knowledge-cutoff disclaimers
NEVER use: as of [date], Up to my last training update, While specific details are limited, based on available information
BAD: "While specific details about the founding are not extensively documented in readily available sources..."
GOOD: "The company was founded in 1994, according to its registration documents."

## 21. Do not use sycophantic or servile tone
NEVER use: Great question!, You're absolutely right!, That's an excellent point!, What a thoughtful...
BAD: "Great question! You're absolutely right that this is a complex topic."
GOOD: "The economic factors you mentioned are relevant here."

## 22. Do not use filler phrases
Replace: "In order to" -> "To", "Due to the fact that" -> "Because", "At this point in time" -> "Now", "It is important to note that" -> (delete), "has the ability to" -> "can"

## 23. Do not hedge excessively
BAD: "It could potentially possibly be argued that the policy might have some effect."
GOOD: "The policy may affect outcomes."

## 24. Do not use generic positive conclusions
NEVER use: The future looks bright, Exciting times lie ahead, journey toward excellence, step in the right direction
BAD: "The future looks bright. Exciting times lie ahead as they continue their journey toward excellence."
GOOD: "The company plans to open two more locations next year."

## 25. Do not over-hyphenate common word pairs
Humans don't hyphenate these consistently: cross-functional, high-quality, data-driven, well-known, real-time, end-to-end. Drop the hyphens for common compounds.
BAD: "The cross-functional team delivered a high-quality, data-driven report."
GOOD: "The cross functional team delivered a high quality, data driven report."
"""
```

Leave `BATCH_HUMANIZE_SYSTEM` and `BATCH_HUMANIZE` as empty strings for now -- they're implemented in Task 2.

```python
BATCH_HUMANIZE_SYSTEM = ""
BATCH_HUMANIZE = ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd simulation && python -m pytest tests/test_humanizer.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add simulation/prompts/humanizer.py simulation/tests/test_humanizer.py
git commit -m "feat: add WRITING_RULES constant with all 25 humanizer categories"
```

---

### Task 2: Add BATCH_HUMANIZE prompt template to `prompts/humanizer.py`

**Files:**
- Modify: `simulation/prompts/humanizer.py`
- Modify: `simulation/tests/test_humanizer.py`

- [ ] **Step 1: Write the tests for BATCH_HUMANIZE**

Append to `simulation/tests/test_humanizer.py`:

```python
def test_batch_humanize_system_is_string():
    from prompts.humanizer import BATCH_HUMANIZE_SYSTEM

    assert isinstance(BATCH_HUMANIZE_SYSTEM, str)
    assert len(BATCH_HUMANIZE_SYSTEM) > 10


def test_batch_humanize_has_comments_json_placeholder():
    from prompts.humanizer import BATCH_HUMANIZE

    assert "{comments_json}" in BATCH_HUMANIZE


def test_batch_humanize_includes_writing_rules():
    from prompts.humanizer import BATCH_HUMANIZE, WRITING_RULES

    # The batch prompt should contain the full rules
    # (either directly or by reference — check a key phrase)
    assert "delve" in BATCH_HUMANIZE.lower() or WRITING_RULES[:50] in BATCH_HUMANIZE


def test_batch_humanize_specifies_json_output():
    from prompts.humanizer import BATCH_HUMANIZE

    assert "json" in BATCH_HUMANIZE.lower()
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `cd simulation && python -m pytest tests/test_humanizer.py -v`
Expected: New tests FAIL (BATCH_HUMANIZE is empty string)

- [ ] **Step 3: Implement BATCH_HUMANIZE_SYSTEM and BATCH_HUMANIZE**

Update `simulation/prompts/humanizer.py`, replacing the empty strings:

```python
BATCH_HUMANIZE_SYSTEM = "You rewrite text to remove AI writing patterns while preserving meaning and voice."

BATCH_HUMANIZE = """Rewrite each comment below to remove AI writing patterns.
Apply these rules:

""" + WRITING_RULES + """

COMMENTS TO REWRITE:
{comments_json}

INSTRUCTIONS:
- Preserve each comment's meaning, tone, approximate length, and persona voice
- ONLY remove AI writing patterns — do not change the substance
- Keep the author's personality and perspective intact
- Return ONLY a JSON array of objects with "id" and "content" keys
- The "id" must match the original comment's "id"
- No surrounding text, no markdown fences, no commentary

OUTPUT FORMAT (JSON array only):
[{{"id": 1, "content": "rewritten text"}}, {{"id": 2, "content": "rewritten text"}}]"""
```

Note: Double braces `{{` and `}}` are needed because this is a `.format()` template — `{comments_json}` is the only placeholder.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd simulation && python -m pytest tests/test_humanizer.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add simulation/prompts/humanizer.py simulation/tests/test_humanizer.py
git commit -m "feat: add BATCH_HUMANIZE prompt template for post-simulation rewriting"
```

---

### Task 3: Add `humanize_comments()` function to `run_simulation.py`

**Files:**
- Modify: `simulation/scripts/run_simulation.py`
- Create: `simulation/tests/test_humanizer_integration.py`

This is the core function. It reads comments from the OASIS DB, sends them through the humanizer LLM, and writes back the rewritten text.

- [ ] **Step 1: Write the test — zero comments is a no-op**

```python
# simulation/tests/test_humanizer_integration.py
# pyright: reportMissingImports=false, reportImplicitRelativeImport=false

import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _create_oasis_db(path: str) -> None:
    """Create a minimal OASIS-schema DB for testing."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE user (
            user_id INTEGER PRIMARY KEY,
            agent_id INTEGER,
            user_name TEXT,
            name TEXT,
            bio TEXT,
            created_at TEXT,
            num_followings INTEGER,
            num_followers INTEGER
        );
        CREATE TABLE post (
            post_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            content TEXT,
            num_likes INTEGER,
            num_dislikes INTEGER,
            created_at TEXT
        );
        CREATE TABLE comment (
            comment_id INTEGER PRIMARY KEY,
            post_id INTEGER,
            user_id INTEGER,
            content TEXT,
            created_at TEXT,
            num_likes INTEGER,
            num_dislikes INTEGER
        );
    """)
    conn.commit()
    conn.close()


@pytest.fixture
def oasis_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    _create_oasis_db(path)
    yield path
    os.unlink(path)


def test_humanize_comments_zero_comments_returns_zero(oasis_db):
    from scripts.run_simulation import humanize_comments

    result = humanize_comments(oasis_db)
    assert result == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd simulation && python -m pytest tests/test_humanizer_integration.py::test_humanize_comments_zero_comments_returns_zero -v`
Expected: FAIL — `ImportError: cannot import name 'humanize_comments'`

- [ ] **Step 3: Implement the skeleton of `humanize_comments()`**

Add these imports to the top of `simulation/scripts/run_simulation.py`, alongside the existing imports:

```python
import sqlite3  # not currently imported — needed for humanize_comments
from prompts.humanizer import BATCH_HUMANIZE, BATCH_HUMANIZE_SYSTEM
```

Note: `ChatAgent` and `BaseMessage` are already imported in `run_simulation.py` via OASIS's internals, but they are NOT explicitly imported at module level. Add them near the existing camel imports (around line 30-31):

```python
from camel.agents import ChatAgent
from camel.messages import BaseMessage
```

These module-level imports are required for the monkeypatch test strategy to work (tests monkeypatch `scripts.run_simulation.ChatAgent`).

Add the function before `main()` (after `run_interviews`):

```python
def humanize_comments(oasis_db_path: str) -> int:
    """Rewrite comments in the OASIS DB to remove AI writing patterns.

    Returns the number of LLM calls made.
    """
    conn = sqlite3.connect(oasis_db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT c.comment_id, COALESCE(u.user_name, u.name) AS author, c.content "
            "FROM comment c JOIN user u ON c.user_id = u.user_id "
            "WHERE c.post_id = 1 "
            "ORDER BY c.created_at"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return 0

    comments = [
        {"id": int(r["comment_id"]), "author": r["author"], "content": r["content"]}
        for r in rows
    ]

    # Chunk into batches of 25
    batch_size = 25
    batches = [comments[i:i + batch_size] for i in range(0, len(comments), batch_size)]
    llm_calls = 0

    # Use temperature=0.3 (not the simulation's 0.8) for precise rewriting
    model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=os.getenv("LLM_MODEL", "gpt-5-mini"),
        api_key=os.getenv("LLM_API_KEY"),
        url=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        model_config_dict={"temperature": 0.3},
    )

    for batch in batches:
        prompt = BATCH_HUMANIZE.format(comments_json=json.dumps(batch, indent=2))
        try:
            agent = ChatAgent(model=model, system_message=BATCH_HUMANIZE_SYSTEM)
            msg = BaseMessage.make_user_message(role_name="User", content=prompt)
            response = agent.step(msg)
            raw = response.msgs[0].content
            llm_calls += 1

            # Strip markdown code fences
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                text = text.rsplit("```", 1)[0]

            rewritten = json.loads(text)
            if not isinstance(rewritten, list):
                print("Warning: humanizer returned non-list, skipping batch")
                continue

            # Write back to OASIS DB
            update_conn = sqlite3.connect(oasis_db_path)
            try:
                for item in rewritten:
                    comment_id = item.get("id")
                    content = item.get("content")
                    if comment_id is not None and content is not None:
                        update_conn.execute(
                            "UPDATE comment SET content = ? WHERE comment_id = ?",
                            (str(content), int(comment_id)),
                        )
                update_conn.commit()
            finally:
                update_conn.close()

        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            print(f"Warning: humanizer batch failed ({exc}), using original comments")
            continue
        except Exception as exc:
            print(f"Warning: humanizer LLM call failed ({exc}), using original comments")
            continue

    return llm_calls
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd simulation && python -m pytest tests/test_humanizer_integration.py::test_humanize_comments_zero_comments_returns_zero -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add simulation/scripts/run_simulation.py simulation/tests/test_humanizer_integration.py
git commit -m "feat: add humanize_comments() skeleton — zero-comments no-op"
```

---

### Task 4: Test `humanize_comments()` with mocked LLM

**Files:**
- Modify: `simulation/tests/test_humanizer_integration.py`

- [ ] **Step 1: Write the test — successful batch rewrite**

Append to `simulation/tests/test_humanizer_integration.py`:

```python
import json


def _seed_oasis_comments(path: str) -> None:
    """Insert a user and two comments into the OASIS DB."""
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO user (user_id, user_name, name, bio, created_at, num_followings, num_followers) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (1, "skeptic_jordan", "Jordan", "PM", "2026-01-01", 0, 0),
    )
    conn.execute(
        "INSERT INTO post (post_id, user_id, content, num_likes, num_dislikes, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (1, 99, "seed post", 0, 0, "2026-01-01"),
    )
    conn.execute(
        "INSERT INTO comment (comment_id, post_id, user_id, content, created_at, num_likes, num_dislikes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (1, 1, 1, "This is a pivotal testament to the evolving landscape.", "2026-01-01T10:00", 0, 0),
    )
    conn.execute(
        "INSERT INTO comment (comment_id, post_id, user_id, content, created_at, num_likes, num_dislikes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (2, 1, 1, "Additionally, it delves into the intricate interplay.", "2026-01-01T10:05", 0, 0),
    )
    conn.commit()
    conn.close()


def test_humanize_comments_rewrites_content(oasis_db, monkeypatch):
    _seed_oasis_comments(oasis_db)

    fake_response = json.dumps([
        {"id": 1, "content": "This is an important step for regional statistics."},
        {"id": 2, "content": "It also explores how these forces interact."},
    ])

    # Mock the ChatAgent to return our fake response
    class FakeResponse:
        def __init__(self):
            self.msgs = [type("Msg", (), {"content": fake_response})()]

    class FakeAgent:
        def __init__(self, **kwargs):
            pass
        def step(self, msg):
            return FakeResponse()

    from scripts import run_simulation
    monkeypatch.setattr(run_simulation, "ChatAgent", FakeAgent)

    calls = run_simulation.humanize_comments(oasis_db)
    assert calls == 1

    # Verify DB was updated
    conn = sqlite3.connect(oasis_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT comment_id, content FROM comment ORDER BY comment_id").fetchall()
    conn.close()

    assert rows[0]["content"] == "This is an important step for regional statistics."
    assert rows[1]["content"] == "It also explores how these forces interact."


def test_humanize_comments_handles_llm_failure(oasis_db, monkeypatch):
    _seed_oasis_comments(oasis_db)

    class FakeAgent:
        def __init__(self, **kwargs):
            pass
        def step(self, msg):
            raise RuntimeError("LLM API timeout")

    from scripts import run_simulation
    monkeypatch.setattr(run_simulation, "ChatAgent", FakeAgent)

    calls = run_simulation.humanize_comments(oasis_db)
    assert calls == 0  # no successful calls

    # Verify DB is unchanged
    conn = sqlite3.connect(oasis_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT comment_id, content FROM comment ORDER BY comment_id").fetchall()
    conn.close()

    assert "pivotal testament" in rows[0]["content"]  # original preserved
    assert "delves into" in rows[1]["content"]  # original preserved


def test_humanize_comments_handles_bad_json(oasis_db, monkeypatch):
    _seed_oasis_comments(oasis_db)

    class FakeResponse:
        def __init__(self):
            self.msgs = [type("Msg", (), {"content": "Sorry, I can't do that."})()]

    class FakeAgent:
        def __init__(self, **kwargs):
            pass
        def step(self, msg):
            return FakeResponse()

    from scripts import run_simulation
    monkeypatch.setattr(run_simulation, "ChatAgent", FakeAgent)

    calls = run_simulation.humanize_comments(oasis_db)
    assert calls == 1  # LLM call succeeded, JSON parse failed

    # Verify DB is unchanged
    conn = sqlite3.connect(oasis_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT comment_id, content FROM comment ORDER BY comment_id").fetchall()
    conn.close()

    assert "pivotal testament" in rows[0]["content"]
```

- [ ] **Step 2: Run tests to verify they fail (import issue or mocking)**

Run: `cd simulation && python -m pytest tests/test_humanizer_integration.py -v`
Expected: New tests may need adjustment — iterate until mocking works correctly

- [ ] **Step 3: Fix any test issues and verify all pass**

Run: `cd simulation && python -m pytest tests/test_humanizer_integration.py -v`
Expected: All 4 tests PASS

- [ ] **Step 4: Commit**

```bash
git add simulation/tests/test_humanizer_integration.py
git commit -m "test: add humanize_comments tests with mocked LLM"
```

---

### Task 5: Wire `humanize_comments()` into the simulation pipeline

**Files:**
- Modify: `simulation/scripts/run_simulation.py:275-289`

- [ ] **Step 1: Modify `run_simulation()` to call `humanize_comments()`**

In `simulation/scripts/run_simulation.py`, find the section after interviews (around line 275-289) and replace:

```python
    emit_progress(phase="complete", llm_calls=llm_calls)

    await env.close()

    # Extract OASIS results AFTER env.close() to ensure all data is flushed to SQLite
    if app_db_path is not None and run_id is not None:
        extract_oasis_results(app_db_path, db_path, run_id, oasis_to_run_agent)
        update_run_status(
            app_db_path,
            run_id,
            "complete",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    return db_path
```

With:

```python
    await env.close()

    # Humanize comments — rewrite AI patterns before extraction
    emit_progress(phase="humanizing", llm_calls=llm_calls)
    print("Humanizing comments...")
    humanizer_calls = humanize_comments(db_path)
    llm_calls += humanizer_calls
    print(f"Humanization complete ({humanizer_calls} LLM calls)")

    # Extract OASIS results AFTER env.close() and humanization
    if app_db_path is not None and run_id is not None:
        extract_oasis_results(app_db_path, db_path, run_id, oasis_to_run_agent)
        update_run_status(
            app_db_path,
            run_id,
            "complete",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    emit_progress(phase="complete", llm_calls=llm_calls)

    return db_path
```

Key changes:
- Removed `emit_progress(phase="complete")` from before `env.close()`
- Added `emit_progress(phase="humanizing")` after `env.close()`
- Added `humanize_comments(db_path)` call
- Moved `emit_progress(phase="complete")` to the very end

- [ ] **Step 2: Verify existing tests still pass**

Run: `cd simulation && python -m pytest tests/ -v --ignore=tests/test_progress.py`
Expected: All tests PASS (test_progress.py may fail due to camel dependency — ignore it)

- [ ] **Step 3: Commit**

```bash
git add simulation/scripts/run_simulation.py
git commit -m "feat: wire humanize_comments() into simulation pipeline"
```

---

### Task 6: Inject WRITING_RULES into suggest.py and rewrite.py

**Files:**
- Modify: `simulation/prompts/suggest.py`
- Modify: `simulation/prompts/rewrite.py`
- Modify: `simulation/tests/test_humanizer.py`

- [ ] **Step 1: Write the tests**

Append to `simulation/tests/test_humanizer.py`:

```python
def test_suggest_system_includes_writing_rules():
    from prompts.suggest import SYSTEM
    from prompts.humanizer import WRITING_RULES

    assert WRITING_RULES in SYSTEM
    assert "authentic" in SYSTEM.lower()  # original content preserved


def test_rewrite_system_includes_writing_rules():
    from prompts.rewrite import REWRITE_SYSTEM
    from prompts.humanizer import WRITING_RULES

    assert WRITING_RULES in REWRITE_SYSTEM
    assert "authentic" in REWRITE_SYSTEM.lower()


def test_analyze_system_unchanged():
    from prompts.rewrite import ANALYZE_SYSTEM

    # ANALYZE_SYSTEM should NOT contain humanizer rules
    assert "delve" not in ANALYZE_SYSTEM.lower() or len(ANALYZE_SYSTEM) < 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd simulation && python -m pytest tests/test_humanizer.py::test_suggest_system_includes_writing_rules tests/test_humanizer.py::test_rewrite_system_includes_writing_rules -v`
Expected: FAIL — WRITING_RULES not in SYSTEM

- [ ] **Step 3: Modify `prompts/suggest.py`**

Replace the `SYSTEM` line in `simulation/prompts/suggest.py`:

```python
from prompts.humanizer import WRITING_RULES

SYSTEM = "You write authentic Reddit launch posts.\n\n" + WRITING_RULES
```

Leave `SUGGEST_POST` unchanged.

- [ ] **Step 4: Modify `prompts/rewrite.py`**

Add import and update `REWRITE_SYSTEM` in `simulation/prompts/rewrite.py`:

```python
from prompts.humanizer import WRITING_RULES
```

Change line 34 from:
```python
REWRITE_SYSTEM = "You write authentic Reddit launch posts."
```
To:
```python
REWRITE_SYSTEM = "You write authentic Reddit launch posts.\n\n" + WRITING_RULES
```

Leave `ANALYZE_SYSTEM`, `ANALYZE`, and `REWRITE` unchanged.

- [ ] **Step 5: Run all tests**

Run: `cd simulation && python -m pytest tests/test_humanizer.py -v`
Expected: All tests PASS

- [ ] **Step 6: Run the full test suite**

Run: `cd simulation && python -m pytest tests/ -v --ignore=tests/test_progress.py`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add simulation/prompts/suggest.py simulation/prompts/rewrite.py simulation/tests/test_humanizer.py
git commit -m "feat: inject WRITING_RULES into suggest and rewrite system prompts"
```

---

### Task 7: Final verification

**Files:** None — verification only

- [ ] **Step 1: Run full test suite**

Run: `cd simulation && python -m pytest tests/ -v --ignore=tests/test_progress.py`
Expected: All tests PASS

- [ ] **Step 2: Verify prompt imports work end-to-end**

Run: `cd simulation && python -c "from prompts.humanizer import WRITING_RULES, BATCH_HUMANIZE, BATCH_HUMANIZE_SYSTEM; print(f'WRITING_RULES: {len(WRITING_RULES)} chars'); print(f'BATCH_HUMANIZE: {len(BATCH_HUMANIZE)} chars'); print(f'SYSTEM: {len(BATCH_HUMANIZE_SYSTEM)} chars')"`
Expected: Prints character counts, no errors

- [ ] **Step 3: Verify suggest.py and rewrite.py load correctly**

Run: `cd simulation && python -c "from prompts.suggest import SYSTEM; from prompts.rewrite import REWRITE_SYSTEM, ANALYZE_SYSTEM; print(f'suggest SYSTEM: {len(SYSTEM)} chars'); print(f'REWRITE_SYSTEM: {len(REWRITE_SYSTEM)} chars'); print(f'ANALYZE_SYSTEM: {len(ANALYZE_SYSTEM)} chars (unchanged)')"`
Expected: suggest SYSTEM and REWRITE_SYSTEM are large (3000+ chars), ANALYZE_SYSTEM is small (~60 chars)

- [ ] **Step 4: Verify humanize_comments imports cleanly**

Run: `cd simulation && python -c "from scripts.run_simulation import humanize_comments; print('humanize_comments imported OK')"`
Expected: Prints success message (may warn about missing camel if not in venv — that's OK)

- [ ] **Step 5: Commit all work if any uncommitted changes remain**

```bash
git status
# If clean, no commit needed
```
