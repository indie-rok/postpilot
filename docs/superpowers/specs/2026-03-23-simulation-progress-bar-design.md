# Simulation Progress Bar

## Overview

Add a compact inline progress strip to the simulation UI that shows current phase, step progress, and running LLM call count during simulation runs.

## Scope

Simulation subprocess only (rounds + interviews). Scorecard generation gets its own separate progress bar later.

## Design Decisions

- **LLM call counter**: Running count only ("23 LLM calls"), no estimated total — actual count as they happen
- **Layout**: Compact inline strip (Option B) — phase pill + thin bar + step text + call counter
- **Log container**: Stays visible below the progress strip — progress is the summary, log is the detail
- **Existing print() calls**: Unchanged. Structured progress lines are additive.

## Architecture

Three layers of changes:

### 1. `run_simulation.py` — Structured progress output

Emit `PROGRESS:{json}\n` lines to stdout alongside existing human-readable `print()` calls. The server parses these; all other lines remain log messages.

#### Progress events

**Setup** — emitted once after calculating rounds, before simulation loop starts:
```json
PROGRESS:{"phase":"setup","total_rounds":8,"total_agents":10}
```

**Simulation round** — emitted at the start of each round, after determining active agents:
```json
PROGRESS:{"phase":"simulation","round":4,"total_rounds":8,"hour":"13:00","active_agents":5,"llm_calls":23}
```

**Interviews start** — emitted once before the interview loop:
```json
PROGRESS:{"phase":"interview","current":0,"total":7}
```

**Interview step** — emitted after each agent interview completes:
```json
PROGRESS:{"phase":"interview","current":3,"total":7,"agent":"skeptic_01","llm_calls":47}
```

**Complete** — emitted after interviews finish, before `env.close()`:
```json
PROGRESS:{"phase":"complete","llm_calls":52}
```

#### LLM call counting

- `llm_calls` counter starts at 0
- Incremented by `len(active_agents)` after each `env.step()` call (each active agent = 1 LLM call)
- Incremented by 1 after each `agent.perform_interview()` call
- The seed post step (ManualAction) does not count as an LLM call

### 2. `server.py` — Parse and broadcast progress

In the `_run` method's stdout reading loop:
- Lines starting with `PROGRESS:` → strip prefix, parse JSON, broadcast as `{"type": "progress", ...merged_json}`
- All other lines → broadcast as `{"type": "log", "message": ...}` (unchanged)

No new endpoints. No new WebSocket channels. Just a new message type on the existing WebSocket.

### 3. `index.html` — Compact inline progress strip

#### HTML structure

New element inside `progress-panel`, above the `log-container`:

```
[PHASE_PILL] [=========>-----------] [Round 4/8] [· 23 calls]
```

- Hidden by default, shown on first `progress` message
- Sits between the `progress-title` ("Running Simulation...") and `log-container`

#### Phase pill states

| Phase | Pill text | Pill color |
|---|---|---|
| setup | SETUP | `var(--border)` gray |
| simulation | SIMULATING | `var(--brand)` orange |
| interview | INTERVIEWING | `var(--success)` green |
| complete | COMPLETE | `var(--success)` green |

#### Progress bar fill

- **setup phase**: 0% (empty bar)
- **simulation phase**: `round / total_rounds` as percentage
- **interview phase**: `current / total` as percentage. If `total` is 0 (no engaged agents), skip straight to complete — no interview strip shown.
- **complete phase**: 100%
- Bar color matches pill color

#### Step text

- **setup**: "Preparing..." 
- **simulation**: "Round 4/8 · 13:00 · 5 agents"
- **interview**: "3/7 · skeptic_01"
- **complete**: "Done"

#### Call counter

Right-aligned: "· 23 calls" — updates on every progress message that includes `llm_calls`.

#### Reset behavior

When a new simulation starts (user clicks Launch), the progress strip resets: hidden until first progress message, counters zeroed.

## Files Changed

| File | Change |
|---|---|
| `simulation/scripts/run_simulation.py` | Add `emit_progress()` helper, call it at setup, each round, interview start, each interview, completion |
| `simulation/server.py` | Parse `PROGRESS:` prefix in stdout loop, broadcast as `{"type":"progress"}` |
| `simulation/static/index.html` | Add progress strip HTML/CSS, handle `progress` WebSocket messages |

## What Does NOT Change

- Existing `print()` statements in `run_simulation.py`
- WebSocket `log`, `done`, `error` message types
- The `done` message still triggers `simulationDone()` as before
- Scorecard/rewrite/analysis endpoints
- No new dependencies
