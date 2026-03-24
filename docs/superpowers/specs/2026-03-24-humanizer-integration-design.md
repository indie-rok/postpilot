# Humanizer Integration Design

Integrate AI-writing-pattern-avoidance rules into the simulation pipeline so all generated text sounds human rather than AI-generated.

## Problem

LLM-generated text — both simulated Reddit comments from OASIS agents and user-facing posts from suggest/rewrite — exhibits recognizable AI writing patterns: em dashes, inflated significance, AI vocabulary ("delve", "leverage", "landscape"), rule-of-three lists, sycophantic tone, etc. This undermines the simulation's realism and the quality of generated launch posts.

## Approach

**Batch post-processing for agent comments.** Rather than injecting rules into every agent's system prompt (which multiplies token cost by agent count per round), let OASIS generate normally, then run a single humanizer LLM call on all comments after the simulation completes.

**System prompt injection for suggest/rewrite.** These are single LLM calls where token overhead is negligible, so the full humanizer rules are appended directly to their system messages.

## Components

### 1. `prompts/humanizer.py` (new file)

Two constants:

- `WRITING_RULES` — The complete humanizer ruleset, sourced from [blader/humanizer SKILL.md](https://github.com/blader/humanizer/blob/main/SKILL.md) (based on Wikipedia's "Signs of AI writing" guide). Contains all 25 categories, each with its "words to watch" list and the rule to follow. Adapted from an editing guide into prompt instruction format ("Do not use...", "Avoid...", "Instead of X, write Y").

  The 25 categories:

  **Content patterns (1-6):**
  1. Undue emphasis on significance/legacy/broader trends — words: "stands as", "testament", "pivotal", "underscores", "evolving landscape"
  2. Undue emphasis on notability/media coverage — words: "independent coverage", "active social media presence"
  3. Superficial -ing analyses — words: "highlighting", "ensuring", "reflecting", "symbolizing", "showcasing"
  4. Promotional/advertisement language — words: "boasts", "vibrant", "nestled", "groundbreaking", "breathtaking", "stunning"
  5. Vague attributions/weasel words — words: "Industry reports", "Experts argue", "Some critics"
  6. Formulaic "Challenges and Future Prospects" sections — words: "Despite its... faces challenges", "Future Outlook"

  **Language/grammar patterns (7-12):**
  7. Overused AI vocabulary — words: "Additionally", "crucial", "delve", "enhance", "fostering", "garner", "interplay", "intricate", "landscape" (abstract), "pivotal", "showcase", "tapestry" (abstract), "testament", "underscore", "vibrant"
  8. Copula avoidance — words: "serves as", "stands as", "boasts", "features" instead of "is"/"has"
  9. Negative parallelisms — "Not only...but...", "It's not just X — it's Y"
  10. Rule of three overuse — forcing ideas into groups of three
  11. Elegant variation / synonym cycling — excessive synonym substitution for the same noun
  12. False ranges — "from X to Y" where X and Y aren't on a meaningful scale

  **Style patterns (13-18):**
  13. Em dash overuse — replace with commas, periods, or parentheses
  14. Overuse of boldface — mechanical emphasis
  15. Inline-header vertical lists — bolded headers with colons in bullet points
  16. Title Case in headings — capitalize all main words
  17. Emojis — decorating headings or bullet points
  18. Curly quotation marks — use straight quotes

  **Communication patterns (19-21):**
  19. Collaborative artifacts — "I hope this helps!", "Certainly!", "Would you like..."
  20. Knowledge-cutoff disclaimers — "as of [date]", "While specific details are limited..."
  21. Sycophantic/servile tone — "Great question!", "You're absolutely right!"

  **Filler and hedging (22-25):**
  22. Filler phrases — "In order to", "Due to the fact that", "It is important to note"
  23. Excessive hedging — "could potentially possibly be argued"
  24. Generic positive conclusions — "The future looks bright", "Exciting times lie ahead"
  25. Hyphenated word pair overuse — over-consistent hyphenation of common compounds

  **Plus the "Personality and Soul" meta-rules:**
  - Vary sentence rhythm (short punchy, then longer)
  - Have opinions, not just neutral reporting
  - Acknowledge complexity and mixed feelings
  - Use first person when it fits
  - Be specific about feelings, not generic

- `BATCH_HUMANIZE_SYSTEM` — System message for the humanizer agent: "You rewrite text to remove AI writing patterns while preserving meaning and voice."

- `BATCH_HUMANIZE` — Prompt template for post-simulation batch rewrite.
  - Input: `{comments_json}` — JSON array of `{id, author, content}` objects
  - Output: JSON array of `{id, content}` with rewritten text
  - Includes `WRITING_RULES` inline
  - Instructions: preserve each comment's meaning, tone, length, and persona voice — only remove AI writing patterns
  - Explicit output constraint: "Return ONLY the JSON array. No surrounding text, no markdown fences, no commentary."

### 2. `scripts/run_simulation.py` changes

New function:

```python
def humanize_comments(oasis_db_path: str) -> int
```

Returns the number of LLM calls made (for the `llm_calls` counter).

**LLM invocation pattern:** Uses the established `ChatAgent.step()` pattern (same as `analyze_and_rewrite.py` and `generate_scorecard.py`):

```python
from camel.agents import ChatAgent
from camel.messages import BaseMessage
from prompts.humanizer import BATCH_HUMANIZE, BATCH_HUMANIZE_SYSTEM

agent = ChatAgent(model=create_model(), system_message=BATCH_HUMANIZE_SYSTEM)
msg = BaseMessage.make_user_message(role_name="User", content=prompt)
response = agent.step(msg)
raw = response.msgs[0].content
```

Note: Creates a separate model with `temperature=0.3` (not the simulation's 0.8) since the humanizer should preserve meaning precisely, not generate creatively.

Steps:

1. Query all comments with author names from the OASIS SQLite DB:
   ```sql
   SELECT c.comment_id, COALESCE(u.user_name, u.name) AS author, c.content
   FROM comment c JOIN user u ON c.user_id = u.user_id
   WHERE c.post_id = 1
   ORDER BY c.created_at
   ```
   Uses `COALESCE(u.user_name, u.name)` to handle OASIS's dual name columns, and `WHERE c.post_id = 1` to filter to the seed post's comments.
2. If zero comments, return 0 immediately (no-op)
3. Build a JSON array of `{id, author, content}` objects
4. If comment count exceeds 25, chunk into batches of 25 and make one LLM call per batch (avoids context window limits)
5. For each batch, send an LLM call using `BATCH_HUMANIZE` prompt
6. Strip markdown code fences from response before parsing JSON (LLMs frequently wrap JSON in ``` fences). Follow the existing `_parse_llm_json` pattern used in `generate_scorecard.py` and `generate_community.py`.
7. Update each comment row: `UPDATE comment SET content = ? WHERE comment_id = ?`
8. Return the number of batches processed (for `llm_calls` counter)

**Placement in `run_simulation()`:** Called **after** `env.close()` (which flushes all pending writes to SQLite) and **before** `extract_oasis_results()`. The existing `emit_progress(phase="complete", llm_calls=llm_calls)` currently sits before `env.close()` — it must be moved to after both humanization and extraction:

```python
# Current code has emit_progress(phase="complete") here — REMOVE it
await env.close()                              # flush OASIS DB
emit_progress(phase="humanizing", ...)
humanizer_calls = humanize_comments(db_path)   # rewrite comments in OASIS DB
llm_calls += humanizer_calls
extract_oasis_results(...)                     # copy humanized text to app DB
emit_progress(phase="complete", llm_calls=llm_calls)  # MOVED here
```

**Error handling:** If the humanizer LLM call fails or returns unparseable JSON, log a warning and skip — use the original comments. The simulation must not fail because the humanizer did.

### 3. `prompts/suggest.py` changes

Append `WRITING_RULES` to the `SYSTEM` constant:

```python
from prompts.humanizer import WRITING_RULES

SYSTEM = "You write authentic Reddit launch posts.\n\n" + WRITING_RULES
```

### 4. `prompts/rewrite.py` changes

Append `WRITING_RULES` to the `REWRITE_SYSTEM` constant:

```python
from prompts.humanizer import WRITING_RULES

REWRITE_SYSTEM = "You write authentic Reddit launch posts.\n\n" + WRITING_RULES
```

`ANALYZE_SYSTEM` is unchanged — analysis reports are internal, not user-facing prose.

## Files touched

| File | Change |
|------|--------|
| `simulation/prompts/humanizer.py` | New. `WRITING_RULES` + `BATCH_HUMANIZE` |
| `simulation/scripts/run_simulation.py` | Add `humanize_comments()`, call after `env.close()` before extraction, reorder progress emissions |
| `simulation/prompts/suggest.py` | Append `WRITING_RULES` to `SYSTEM` |
| `simulation/prompts/rewrite.py` | Append `WRITING_RULES` to `REWRITE_SYSTEM` |

## Files not touched

- `prompts/simulation.py` — interview prompt is structured Q&A ("What does this product do?"), not free-form prose. Interviews ask agents to reflect on the post; the format is analytical, not conversational, so humanizer rules would distort the intent.
- `prompts/community.py` — persona generation outputs JSON
- `prompts/scanner.py` — product profile outputs JSON
- `prompts/scorecard.py` — comment classification outputs JSON
- `prompts/report.py` — internal analysis reports, not user-facing prose
- `server.py` — no changes needed
- `db.py` — no schema changes
- OASIS source code — no modifications

## Data flow

```
Simulation loop (OASIS generates raw comments)
    ↓
Interviews complete
    ↓
env.close() — flushes all pending writes to OASIS SQLite DB
    ↓
emit_progress(phase="humanizing")
    ↓
humanize_comments(db_path) — LLM call(s) rewrite comments in OASIS DB
    ↓
extract_oasis_results() — copies humanized comments to app DB
    ↓
emit_progress(phase="complete")
    ↓
Scorecard, report, UI — all see humanized text
```

## Error handling

- If the humanizer LLM call fails (network error, timeout): log warning, skip humanization, proceed with raw comments
- If the LLM returns unparseable JSON: log warning, skip humanization
- If individual comment IDs in the response don't match: skip unmatched, update matched ones
- Zero comments: skip LLM call entirely (no-op)
- The simulation run status still transitions to "complete" regardless of humanizer success
