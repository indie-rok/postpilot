# Simulation Progress Bar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact inline progress strip showing phase, step progress, and LLM call count during simulation runs.

**Architecture:** `run_simulation.py` emits `PROGRESS:{json}` lines to stdout alongside existing prints. `server.py` parses the prefix and broadcasts structured `{"type":"progress"}` WebSocket messages. `index.html` renders a compact strip (phase pill + bar + step text + call counter) above the log container.

**Tech Stack:** Python (stdout JSON), FastAPI WebSocket, vanilla JS/CSS

**Spec:** `docs/superpowers/specs/2026-03-23-simulation-progress-bar-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `simulation/scripts/run_simulation.py` | Modify | Add `emit_progress()` helper and 5 call sites |
| `simulation/server.py` | Modify | Parse `PROGRESS:` lines, broadcast as progress messages |
| `simulation/static/index.html` | Modify | Progress strip UI + WebSocket handler |
| `simulation/tests/test_progress.py` | Create | Tests for `emit_progress()` output format |

---

### Task 1: Test `emit_progress()` output format

**Files:**
- Create: `simulation/tests/test_progress.py`

- [ ] **Step 1: Write tests for `emit_progress`**

```python
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.run_simulation import emit_progress


def test_emit_progress_writes_prefixed_json(capsys):
    emit_progress(phase="setup", total_rounds=8, total_agents=10)
    captured = capsys.readouterr()
    assert captured.out.startswith("PROGRESS:")
    payload = json.loads(captured.out.removeprefix("PROGRESS:"))
    assert payload["phase"] == "setup"
    assert payload["total_rounds"] == 8
    assert payload["total_agents"] == 10


def test_emit_progress_simulation_round(capsys):
    emit_progress(
        phase="simulation",
        round=3,
        total_rounds=8,
        hour="11:00",
        active_agents=5,
        llm_calls=15,
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out.removeprefix("PROGRESS:"))
    assert payload["phase"] == "simulation"
    assert payload["round"] == 3
    assert payload["llm_calls"] == 15


def test_emit_progress_interview(capsys):
    emit_progress(
        phase="interview", current=2, total=7, agent="skeptic_01", llm_calls=40
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out.removeprefix("PROGRESS:"))
    assert payload["phase"] == "interview"
    assert payload["current"] == 2
    assert payload["agent"] == "skeptic_01"


def test_emit_progress_complete(capsys):
    emit_progress(phase="complete", llm_calls=52)
    captured = capsys.readouterr()
    payload = json.loads(captured.out.removeprefix("PROGRESS:"))
    assert payload["phase"] == "complete"
    assert payload["llm_calls"] == 52


def test_emit_progress_ends_with_newline(capsys):
    emit_progress(phase="setup", total_rounds=4, total_agents=6)
    captured = capsys.readouterr()
    assert captured.out.endswith("\n")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest simulation/tests/test_progress.py -v`
Expected: FAIL — `emit_progress` does not exist yet.

---

### Task 2: Implement `emit_progress()` in `run_simulation.py`

**Files:**
- Modify: `simulation/scripts/run_simulation.py`

- [ ] **Step 1: Add `emit_progress` function**

Add after the existing imports, before `load_profiles`:

```python
def emit_progress(**kwargs: int | str) -> None:
    print(f"PROGRESS:{json.dumps(kwargs)}", flush=True)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest simulation/tests/test_progress.py -v`
Expected: All 5 pass.

- [ ] **Step 3: Commit**

```bash
git add simulation/scripts/run_simulation.py simulation/tests/test_progress.py
git commit -m "feat: add emit_progress() helper with tests"
```

---

### Task 3: Wire progress calls into `run_simulation()`

**Files:**
- Modify: `simulation/scripts/run_simulation.py` — the `run_simulation()` async function (line ~116) and `run_interviews()` (line ~208)

There are 5 call sites. Add a `llm_calls` counter variable. Do NOT remove or change any existing `print()` calls.

- [ ] **Step 1: Add setup progress + llm_calls counter**

Inside `run_simulation()`, after `total_rounds` is calculated (after line 124) and before the `print(f"Simulating...")` line:

```python
    llm_calls = 0
    emit_progress(phase="setup", total_rounds=total_rounds, total_agents=len(profiles))
```

- [ ] **Step 2: Add simulation round progress**

Inside the `for round_num in range(total_rounds):` loop, after the `active = get_active_agents_for_hour(...)` call and the existing `print(f"Active agents: ...")` line, add:

```python
        simulated_time = f"{simulated_hour:02d}:{simulated_minutes % 60:02d}"
        emit_progress(
            phase="simulation",
            round=round_num + 1,
            total_rounds=total_rounds,
            hour=simulated_time,
            active_agents=len(active),
            llm_calls=llm_calls,
        )
```

After the `await env.step(round_actions)` call, increment the counter:

```python
        llm_calls += len(active)
```

- [ ] **Step 3: Pass `llm_calls` into `run_interviews` and add interview progress**

Change the `run_interviews` signature to accept and return `llm_calls`:

```python
async def run_interviews(agents: list, engaged_ids: set[int], llm_calls: int = 0) -> tuple[list[dict], int]:
```

At the top of `run_interviews`, after the skipped log, calculate the interview total and guard against zero:

```python
    interview_total = sum(1 for aid, _ in agents if aid in engaged_ids)
    if interview_total == 0:
        return ([], llm_calls)
    emit_progress(phase="interview", current=0, total=interview_total)
```

Add a counter `interview_idx = 0` before the loop. After each successful or failed interview (at the end of each loop iteration), increment and emit:

```python
        interview_idx += 1
        llm_calls += 1
        emit_progress(
            phase="interview",
            current=interview_idx,
            total=interview_total,
            agent=username,
            llm_calls=llm_calls,
        )
```

Return `(results, llm_calls)` at the end instead of just `results`.

- [ ] **Step 4: Add complete progress and update the call site**

Update the `run_interviews` call in `run_simulation()`:

```python
    interviews, llm_calls = await run_interviews(agents, engaged_agent_ids, llm_calls)
```

After `interviews_path` is written and the print statement, add:

```python
    emit_progress(phase="complete", llm_calls=llm_calls)
```

- [ ] **Step 5: Verify nothing is broken**

Run: `python -m pytest simulation/tests/ -v`
Expected: All tests pass (including the new progress tests).

- [ ] **Step 6: Commit**

```bash
git add simulation/scripts/run_simulation.py
git commit -m "feat: emit structured progress events during simulation"
```

---

### Task 4: Parse progress lines in `server.py`

**Files:**
- Modify: `simulation/server.py` — the `_run` method's stdout reading loop (around line 195)

- [ ] **Step 1: Add progress line parsing**

In the `_run` method, find the line:

```python
                if msg:
                    await self.broadcast({"type": "log", "message": msg})
```

Replace with:

```python
                if msg:
                    if msg.startswith("PROGRESS:"):
                        try:
                            progress_data = json.loads(msg[9:])
                            progress_data["type"] = "progress"
                            await self.broadcast(progress_data)
                        except json.JSONDecodeError:
                            await self.broadcast({"type": "log", "message": msg})
                    else:
                        await self.broadcast({"type": "log", "message": msg})
```

- [ ] **Step 2: Verify server still starts**

Run: `cd simulation && python -c "from server import app; print('OK')"`
Expected: Prints `OK` without errors.

- [ ] **Step 3: Commit**

```bash
git add simulation/server.py
git commit -m "feat: parse PROGRESS: lines and broadcast as progress events"
```

---

### Task 5: Add progress strip UI to `index.html`

**Files:**
- Modify: `simulation/static/index.html`

- [ ] **Step 1: Add CSS for the progress strip**

Add before the closing `</style>` tag (line ~315):

```css
    .progress-strip {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 13px;
      padding: 12px;
      background: var(--bg);
      border-radius: 4px;
      margin-bottom: 12px;
    }
    .progress-pill {
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 600;
      color: #fff;
      white-space: nowrap;
      text-transform: uppercase;
    }
    .progress-bar-bg {
      flex: 1;
      height: 4px;
      border-radius: 2px;
      background: var(--border);
      overflow: hidden;
    }
    .progress-bar-fill {
      height: 100%;
      border-radius: 2px;
      transition: width 0.3s ease;
    }
    .progress-step { color: var(--text); white-space: nowrap; }
    .progress-calls { color: var(--muted); white-space: nowrap; }
```

- [ ] **Step 2: Add HTML for the progress strip**

Inside the `progress-panel` div (after the `h2#progress-title` element, before the `log-container` div), add:

```html
        <div class="progress-strip hidden" id="progress-strip">
          <span class="progress-pill" id="progress-pill">SETUP</span>
          <div class="progress-bar-bg">
            <div class="progress-bar-fill" id="progress-fill" style="width: 0%;"></div>
          </div>
          <span class="progress-step" id="progress-step">Preparing...</span>
          <span class="progress-calls" id="progress-calls"></span>
        </div>
```

- [ ] **Step 3: Add JS references and handler**

In the `// Elements` section at the top of the script block, add:

```javascript
    const progressStrip = document.getElementById('progress-strip');
    const progressPill = document.getElementById('progress-pill');
    const progressFill = document.getElementById('progress-fill');
    const progressStep = document.getElementById('progress-step');
    const progressCalls = document.getElementById('progress-calls');
```

Add a new function before the `connectWebSocket` function:

```javascript
    function updateProgress(data) {
      progressStrip.classList.remove('hidden');

      const colors = {
        setup: 'var(--border)',
        simulation: 'var(--brand)',
        interview: 'var(--success)',
        complete: 'var(--success)',
      };
      const labels = {
        setup: 'SETUP',
        simulation: 'SIMULATING',
        interview: 'INTERVIEWING',
        complete: 'COMPLETE',
      };

      const color = colors[data.phase] || 'var(--border)';
      progressPill.textContent = labels[data.phase] || data.phase;
      progressPill.style.backgroundColor = color;
      progressFill.style.backgroundColor = color;

      let pct = 0;
      let step = '';

      if (data.phase === 'setup') {
        pct = 0;
        step = 'Preparing...';
      } else if (data.phase === 'simulation') {
        pct = (data.round / data.total_rounds) * 100;
        step = 'Round ' + data.round + '/' + data.total_rounds;
        if (data.hour) step += ' \u00b7 ' + data.hour;
        if (data.active_agents != null) step += ' \u00b7 ' + data.active_agents + ' agents';
      } else if (data.phase === 'interview') {
        pct = data.total > 0 ? (data.current / data.total) * 100 : 100;
        step = data.current + '/' + data.total;
        if (data.agent) step += ' \u00b7 ' + data.agent;
      } else if (data.phase === 'complete') {
        pct = 100;
        step = 'Done';
      }

      progressFill.style.width = pct + '%';
      progressStep.textContent = step;

      if (data.llm_calls != null) {
        progressCalls.textContent = '\u00b7 ' + data.llm_calls + ' calls';
      }
    }
```

- [ ] **Step 4: Wire progress handler into WebSocket onmessage**

In the `ws.onmessage` handler, add a case for the `progress` type. Find:

```javascript
          if (data.type === 'log') {
            appendLog(data.message);
          } else if (data.type === 'done') {
```

Add before `} else if (data.type === 'done')`:

```javascript
          } else if (data.type === 'progress') {
            updateProgress(data);
```

- [ ] **Step 5: Reset progress strip on new simulation**

In the `launchBtn` click handler, after `logContainer.innerHTML = '';`, add:

```javascript
      progressStrip.classList.add('hidden');
      progressFill.style.width = '0%';
      progressCalls.textContent = '';
```

- [ ] **Step 6: Verify no import/syntax errors**

Quick check that the server module still imports cleanly after the HTML changes:

```bash
cd simulation && python -c "from server import app; print('OK')"
```

Expected: Prints `OK`. This confirms no Python-level breakage. Full browser verification is covered in Task 6.

- [ ] **Step 7: Commit**

```bash
git add simulation/static/index.html
git commit -m "feat: add simulation progress strip UI"
```

---

### Task 6: Manual integration test

- [ ] **Step 1: Start the server**

```bash
cd simulation && source .venv/bin/activate && uvicorn server:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: Run a simulation from the UI**

Open `http://localhost:8000`, configure 4 agents / 1 hour, and launch. Verify:

1. Progress strip appears after first progress message
2. Pill shows SETUP → SIMULATING → INTERVIEWING → COMPLETE
3. Bar fills progressively during simulation rounds
4. Bar fills progressively during interviews
5. Step text updates with round numbers, simulated time, agent names
6. Call counter increments
7. Log container still shows raw logs below the strip
8. On completion, pill turns green with "Done"

- [ ] **Step 3: Run a second simulation**

Click Launch again. Verify the progress strip resets and tracks the new run correctly.
