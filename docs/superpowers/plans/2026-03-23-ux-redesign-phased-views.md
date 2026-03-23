# UX Redesign: Phased Views — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the single-page simulation UI into a multi-view app with Setup, Dashboard, Add Community, and Simulation views — each at its own URL.

**Architecture:** FastAPI catch-all serves `index.html` for all non-API routes. A ~30-line client-side History API router swaps view containers. Product data stored in a new `product` table. Existing simulation logic untouched.

**Tech Stack:** Python/FastAPI (backend), vanilla JS + History API (frontend), SQLite (DB)

**Spec:** `docs/superpowers/specs/2026-03-23-ux-redesign-phased-views.md`

**Mockups** (reference only, delete after implementation):
- `simulation/static/mockup-dashboard.html`
- `simulation/static/mockup-add-community.html`
- `simulation/static/mockup-simulate.html`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `simulation/db.py` | Modify | Add `product` table to schema, add product CRUD functions, add community_id filter to `list_runs` |
| `simulation/server.py` | Modify | Add `GET/POST /api/product`, add `?community_id` param to `GET /api/runs`, replace static file mount with SPA catch-all |
| `simulation/static/index.html` | Rewrite | 4 view containers (setup, dashboard, add-community, simulate), client-side router, all view JS |
| `simulation/tests/test_db.py` | Modify | Add product CRUD tests |
| `simulation/tests/test_run_creation.py` | Modify | Add `list_runs` community filter test |

---

## Task 1: Product table + CRUD in db.py

**Files:**
- Modify: `simulation/db.py` — add product table to `SCHEMA_SQL`, add `get_product`, `save_product` functions
- Test: `simulation/tests/test_db.py`

- [ ] **Step 1: Add product table to SCHEMA_SQL**

In `simulation/db.py`, append to the `SCHEMA_SQL` string, after the `run_scorecard` table:

```sql
CREATE TABLE IF NOT EXISTS product (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL,
    tagline TEXT,
    description TEXT,
    features TEXT,
    pricing TEXT,
    target_audience TEXT,
    llm_model TEXT,
    llm_base_url TEXT,
    llm_api_key TEXT,
    batch_size INTEGER DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
```

The `CHECK (id = 1)` constraint ensures only one product row exists.

- [ ] **Step 2: Add `get_product` function**

Add to `simulation/db.py` in the Community CRUD section:

```python
def get_product(db_path: str) -> dict[str, Any] | None:
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM product WHERE id = 1").fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()
```

- [ ] **Step 3: Add `save_product` function**

```python
def save_product(db_path: str, data: dict[str, Any]) -> None:
    conn = get_connection(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        _ = conn.execute(
            """
            INSERT INTO product (id, name, tagline, description, features, pricing,
                target_audience, llm_model, llm_base_url, llm_api_key, batch_size,
                created_at, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                tagline = excluded.tagline,
                description = excluded.description,
                features = excluded.features,
                pricing = excluded.pricing,
                target_audience = excluded.target_audience,
                llm_model = excluded.llm_model,
                llm_base_url = excluded.llm_base_url,
                llm_api_key = excluded.llm_api_key,
                batch_size = excluded.batch_size,
                updated_at = excluded.updated_at
            """,
            (
                data.get("name", ""),
                data.get("tagline"),
                data.get("description"),
                data.get("features"),
                data.get("pricing"),
                data.get("target_audience"),
                data.get("llm_model"),
                data.get("llm_base_url"),
                data.get("llm_api_key"),
                data.get("batch_size", 0),
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Add `community_id` filter to `list_runs`**

Modify `list_runs` in `simulation/db.py` to accept an optional `community_id` parameter:

```python
def list_runs(db_path: str, community_id: int | None = None) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        query = """
            SELECT
                r.id, r.tag, r.status, r.community_id, r.agent_count,
                r.total_hours, r.llm_model, r.post_likes, r.post_dislikes,
                r.created_at, r.completed_at,
                (SELECT COUNT(*) FROM run_comment rc WHERE rc.run_id = r.id) AS comment_count
            FROM run r
        """
        params: list[Any] = []
        if community_id is not None:
            query += " WHERE r.community_id = ?"
            params.append(community_id)
        query += " ORDER BY r.created_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
```

Note: this also adds `r.community_id` to the SELECT which wasn't there before — needed by the dashboard.

- [ ] **Step 5: Write tests**

Add to `simulation/tests/test_db.py`:

```python
def test_get_product_returns_none_when_empty(db_path):
    init_db(db_path)
    assert get_product(db_path) is None

def test_save_and_get_product(db_path):
    init_db(db_path)
    save_product(db_path, {"name": "TestApp", "tagline": "A test app", "description": "Does testing"})
    product = get_product(db_path)
    assert product is not None
    assert product["name"] == "TestApp"
    assert product["tagline"] == "A test app"

def test_save_product_upserts(db_path):
    init_db(db_path)
    save_product(db_path, {"name": "V1"})
    save_product(db_path, {"name": "V2", "tagline": "Updated"})
    product = get_product(db_path)
    assert product["name"] == "V2"
    assert product["tagline"] == "Updated"
```

Add imports: `from db import get_product, save_product`

- [ ] **Step 6: Run tests**

Run: `cd simulation && source .venv/bin/activate && python -m pytest tests/test_db.py -v`
Expected: all pass

- [ ] **Step 7: Commit**

```
git add simulation/db.py simulation/tests/test_db.py
git commit -m "feat: add product table + CRUD, add community_id filter to list_runs"
```

---

## Task 2: Product API endpoints + runs filter + SPA catch-all

**Files:**
- Modify: `simulation/server.py` — add product endpoints, modify runs endpoint, replace static mount with catch-all

- [ ] **Step 1: Add imports**

Add `get_product, save_product` to the imports from `db`.

- [ ] **Step 2: Add product endpoints**

Add before the `/api/runs` endpoint:

```python
class ProductRequest(BaseModel):
    name: str = Field(min_length=1)
    tagline: str | None = None
    description: str | None = None
    features: str | None = None
    pricing: str | None = None
    target_audience: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    batch_size: int = 0


@app.get("/api/product")
async def get_product_endpoint() -> JSONResponse:
    product = get_product(APP_DB)
    if product is None:
        raise HTTPException(status_code=404, detail="No product configured")
    return JSONResponse(content=product)


@app.post("/api/product")
async def save_product_endpoint(request: ProductRequest) -> dict[str, str]:
    save_product(APP_DB, request.model_dump())
    return {"status": "saved"}
```

- [ ] **Step 3: Add community_id query param to GET /api/runs**

Replace the existing `get_runs` endpoint:

```python
@app.get("/api/runs")
async def get_runs(community_id: int | None = None) -> JSONResponse:
    runs = list_runs(APP_DB, community_id=community_id)
    return JSONResponse(content=runs)
```

- [ ] **Step 4: Replace static file mount with SPA catch-all**

Remove the `app.mount("/", StaticFiles(...))` at the bottom of `server.py`. Replace with:

```python
app.mount("/static", StaticFiles(directory=str(STATIC_DIR), check_dir=False), name="static")


@app.get("/{path:path}")
async def spa_catch_all(path: str) -> HTMLResponse:
    index_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
```

This means CSS/JS/images go under `/static/` prefix, and all other non-API routes serve `index.html`.

Important: any `<link>` or `<script>` tags in `index.html` referencing relative paths will need updating to `/static/` if they exist. Currently there are none (everything is inline).

- [ ] **Step 5: Verify server loads**

Run: `cd simulation && source .venv/bin/activate && python -c "from server import app; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```
git add simulation/server.py
git commit -m "feat: add product API, community filter on runs, SPA catch-all route"
```

---

## Task 3: Client-side router + view skeleton

**Files:**
- Modify: `simulation/static/index.html` — add router, add 4 view containers, wire navigation

This is the largest task. The current `index.html` is ~1600 lines. The approach:
1. Add a `<div id="app">` wrapper containing 4 view divs (only one visible at a time)
2. Move all existing simulation UI into `<div id="view-simulate">`
3. Add empty containers for `view-setup`, `view-dashboard`, `view-add-community`
4. Add a router that reads `window.location.pathname` and shows the right view

- [ ] **Step 1: Add view wrapper**

Wrap the existing `<header>` and `<div class="grid">` in a view container. Add the other 3 view containers before it. The structure should be:

```html
<div id="app">
  <div id="view-setup" class="view hidden">...</div>
  <div id="view-dashboard" class="view hidden">...</div>
  <div id="view-add-community" class="view hidden">...</div>
  <div id="view-simulate" class="view hidden">
    <!-- existing header + grid content moves here -->
  </div>
</div>
```

CSS for views:
```css
.view { display: none; }
.view.active { display: block; }
```

- [ ] **Step 2: Add router JS**

At the top of the `<script>` block, add:

```javascript
const routes = {
  '/setup': 'view-setup',
  '/dashboard': 'view-dashboard',
  '/communities/new': 'view-add-community',
};

function navigateTo(url) {
  history.pushState(null, '', url);
  routeToView();
}

function routeToView() {
  const path = window.location.pathname;
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));

  if (path.startsWith('/simulate/')) {
    document.getElementById('view-simulate').classList.add('active');
    const communityId = parseInt(path.split('/')[2]);
    if (communityId) initSimulateView(communityId);
    return;
  }

  const viewId = routes[path];
  if (viewId) {
    document.getElementById(viewId).classList.add('active');
    if (viewId === 'view-dashboard') initDashboard();
    if (viewId === 'view-setup') initSetup();
    if (viewId === 'view-add-community') initAddCommunity();
    return;
  }

  checkProductAndRoute();
}

async function checkProductAndRoute() {
  try {
    const resp = await fetch('/api/product');
    if (resp.ok) {
      navigateTo('/dashboard');
    } else {
      navigateTo('/setup');
    }
  } catch (e) {
    navigateTo('/setup');
  }
}

window.addEventListener('popstate', routeToView);
```

On page load, call `routeToView()` instead of the current initialization.

- [ ] **Step 3: Stub the init functions**

Add placeholder functions that will be fleshed out in subsequent tasks:

```javascript
function initSetup() { /* Task 4 */ }
function initDashboard() { /* Task 5 */ }
function initAddCommunity() { /* Task 6 */ }
function initSimulateView(communityId) { /* Task 7 */ }
```

- [ ] **Step 4: Verify routing works**

Start server: `cd simulation && source .venv/bin/activate && python -m uvicorn server:app --port 8000`

Verify catch-all serves HTML for SPA routes:
```bash
curl -s http://localhost:8000/dashboard | grep '<div id="view-dashboard"'
curl -s http://localhost:8000/setup | grep '<div id="view-setup"'
curl -s http://localhost:8000/simulate/1 | grep '<div id="view-simulate"'
```
Expected: each curl returns a line containing the view div (same HTML served for all routes).

Verify API routes still work:
```bash
curl -s http://localhost:8000/api/reddit-status
```
Expected: `{"configured":true}` (not the HTML page).

- [ ] **Step 5: Commit**

```
git add simulation/static/index.html
git commit -m "feat: add client-side router with 4 view containers"
```

---

## Task 4: Setup view

**Files:**
- Modify: `simulation/static/index.html` — populate `view-setup` HTML + `initSetup()` JS

- [ ] **Step 1: Add Setup HTML**

Inside `<div id="view-setup">`, add:
- Centered layout (max-width 600px)
- Title: "Set up your product"
- Subtitle: "Tell us about your product so simulations can be tailored to it"
- Form fields: name (required), tagline, description (textarea), features (textarea), pricing, target_audience
- "Save & Continue" button

- [ ] **Step 2: Implement `initSetup()`**

```javascript
async function initSetup() {
  // Try to load company.md content for pre-fill
  // (This would be a future feature — for now just show empty form)
}
```

- [ ] **Step 3: Add form submit handler**

On "Save & Continue" click:
1. Collect form values
2. `POST /api/product` with the data
3. On success: `navigateTo('/dashboard')`

- [ ] **Step 4: Verify via API**

With server running (`cd simulation && source .venv/bin/activate && python -m uvicorn server:app --port 8000`):

```bash
# Verify no product exists initially (fresh DB)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/product
# Expected: 404

# Save a product
curl -s -X POST http://localhost:8000/api/product \
  -H "Content-Type: application/json" \
  -d '{"name":"TestApp","tagline":"A test","llm_model":"gpt-5-mini"}'
# Expected: {"status":"saved"}

# Verify product is saved
curl -s http://localhost:8000/api/product | python -c "import sys,json; d=json.load(sys.stdin); print(d['name'], d['llm_model'])"
# Expected: TestApp gpt-5-mini
```

Then open `http://localhost:8000/` in browser (chrome-devtools navigate_page) and verify the router redirects to `/dashboard` (since product now exists).

- [ ] **Step 5: Commit**

```
git add simulation/static/index.html
git commit -m "feat: setup view with product form"
```

---

## Task 5: Dashboard view

**Files:**
- Modify: `simulation/static/index.html` — populate `view-dashboard` HTML + `initDashboard()` JS

Reference mockup: `simulation/static/mockup-dashboard.html`

- [ ] **Step 1: Add Dashboard HTML structure**

Inside `<div id="view-dashboard">`:
- Product bar: icon + name + tagline + Settings button
- Communities section: `<div id="community-grid" class="community-grid">`
- Recent runs section: `<table id="dashboard-runs">`
- Settings slide-out panel: `<div id="settings-panel" class="settings-panel hidden">`

- [ ] **Step 2: Add Dashboard CSS**

Copy relevant styles from `mockup-dashboard.html`:
- `.product-bar`, `.community-grid`, `.community-card`, `.community-card.add-new`
- `.runs-table`, `.grade-badge`, `.settings-panel` (slide-out)

- [ ] **Step 3: Implement `initDashboard()`**

```javascript
async function initDashboard() {
  const [productResp, commResp, runsResp] = await Promise.all([
    fetch('/api/product'),
    fetch('/api/communities'),
    fetch('/api/runs'),
  ]);

  if (!productResp.ok) { navigateTo('/setup'); return; }

  const product = await productResp.json();
  const communities = await commResp.json();
  const runs = await runsResp.json();

  renderProductBar(product);
  renderCommunityGrid(communities);
  renderDashboardRuns(runs);
}
```

- [ ] **Step 4: Implement render functions**

`renderProductBar(product)` — fills product name/tagline in the bar.

`renderCommunityGrid(communities)` — for each community, create a card with: subreddit name, `profile_count` personas, run count (from runs data), "Simulate" button that calls `navigateTo('/simulate/' + community.id)`. Last card is always "+ Add community" that calls `navigateTo('/communities/new')`.

`renderDashboardRuns(runs)` — populates the runs table. Each row clickable — `navigateTo('/simulate/' + run.community_id + '?run=' + run.tag)`.

- [ ] **Step 5: Implement Settings slide-out**

Settings button click → toggle `.settings-panel.active`. Panel contains:
- Product form (same fields as setup, pre-filled)
- LLM settings (model, endpoint, API key, batch size)
- Save button that `POST /api/product`

- [ ] **Step 6: Verify via browser**

With server running (`cd simulation && source .venv/bin/activate && python -m uvicorn server:app --port 8000`):

1. Use chrome-devtools `navigate_page` to `http://localhost:8000/dashboard`
2. Use `take_snapshot` to verify: product name visible, community cards present, runs table present
3. Use `click` on a Simulate button → verify URL changes to `/simulate/:id` via `take_snapshot`
4. Use `navigate_page` back to `/dashboard`, click Settings → verify panel shows with LLM fields via `take_snapshot`

API verification:
```bash
curl -s http://localhost:8000/api/communities | python -c "import sys,json; d=json.load(sys.stdin); print(len(d), 'communities')"
curl -s "http://localhost:8000/api/runs?community_id=1" | python -c "import sys,json; d=json.load(sys.stdin); print(len(d), 'runs')"
```

- [ ] **Step 7: Commit**

```
git add simulation/static/index.html
git commit -m "feat: dashboard view with community cards, runs table, settings panel"
```

---

## Task 6: Add Community view

**Files:**
- Modify: `simulation/static/index.html` — populate `view-add-community` HTML + `initAddCommunity()` JS

Reference mockup: `simulation/static/mockup-add-community.html`

- [ ] **Step 1: Add HTML structure**

Inside `<div id="view-add-community">`:
- Top bar with product info + "← Back to Dashboard" link
- Centered content (max-width 700px)
- Title: "Add Community"
- Subreddit text input
- Persona count slider (3–30, default 18)
- "Generate" button
- Persona review grid (2-column, `<div id="new-persona-grid">`)
- "Cancel" + "Save Community" buttons at bottom

- [ ] **Step 2: Add CSS**

Copy relevant styles from `mockup-add-community.html`:
- Step layout, persona grid (2-column), action buttons

- [ ] **Step 3: Implement `initAddCommunity()`**

Reset the form state: clear subreddit input, reset slider to 18, hide persona grid.

- [ ] **Step 4: Wire Generate button**

On click:
1. Read subreddit + persona count from inputs
2. Show spinner on button
3. `POST /api/communities/generate` with `{ subreddit, persona_count }`
4. On success: render persona cards in the 2-column grid
5. Show Save Community button

Reuse the existing `renderPersonas()` function logic or adapt it for the 2-column layout.

- [ ] **Step 5: Wire Edit/Remove on persona cards**

Reuse the existing edit modal (`#edit-modal`) from the current UI. On Edit click → open modal with persona data. On Save → `PUT /api/communities/profiles/:id`. On Remove → `DELETE /api/communities/profiles/:id`.

- [ ] **Step 6: Wire Save Community button**

On click: `navigateTo('/dashboard')`. The community is already saved to DB by the generate endpoint — Save just confirms and navigates.

Cancel button: `navigateTo('/dashboard')`.

- [ ] **Step 7: Verify via browser**

With server running:

1. Use chrome-devtools `navigate_page` to `http://localhost:8000/communities/new`
2. Use `take_snapshot` to verify: subreddit input, persona slider, Generate button visible
3. Use `fill` on subreddit input with "r/SaaS", `click` Generate
4. Use `wait_for` with text "personas" to confirm generation completes
5. Use `take_snapshot` to verify persona cards appear with Edit/Remove buttons
6. Use `click` on Save Community → verify URL changes to `/dashboard`
7. Use `take_snapshot` on dashboard to verify new community card appears

- [ ] **Step 8: Commit**

```
git add simulation/static/index.html
git commit -m "feat: add community view with subreddit input, persona slider, generation"
```

---

## Task 7: Simulation view refactor

**Files:**
- Modify: `simulation/static/index.html` — refactor existing simulation UI into `view-simulate`

Reference mockup: `simulation/static/mockup-simulate.html`

- [ ] **Step 1: Add top bar to simulation view**

Replace the current `<header>` (FlowPulse title) with:
```html
<div class="sim-top-bar">
  <a href="#" onclick="navigateTo('/dashboard'); return false;" class="back-link">← Dashboard</a>
  <span class="community-badge" id="sim-community-name"></span>
  <span class="persona-count" id="sim-persona-count"></span>
</div>
```

- [ ] **Step 2: Remove community-section from simulation view**

Delete the entire `<div id="community-section">` block (subreddit input, generate button, persona cards, no-reddit notice). This is now handled by the Add Community view.

- [ ] **Step 3: Implement `initSimulateView(communityId)`**

```javascript
async function initSimulateView(communityId) {
  activeCommunityId = communityId;

  // Load community info + product defaults in parallel
  const [commResp, productResp] = await Promise.all([
    fetch('/api/communities'),
    fetch('/api/product'),
  ]);
  const communities = await commResp.json();
  const community = communities.find(c => c.id === communityId);
  if (community) {
    document.getElementById('sim-community-name').textContent = community.subreddit;
    document.getElementById('sim-persona-count').textContent = community.profile_count + ' personas';
  }

  // Hydrate LLM settings from saved product defaults
  if (productResp.ok) {
    const product = await productResp.json();
    if (product.llm_model) llmModelInput.value = product.llm_model;
    if (product.llm_base_url) baseUrlInput.value = product.llm_base_url;
    if (product.llm_api_key) apiKeyInput.value = product.llm_api_key;
    if (product.batch_size != null) batchSizeInput.value = product.batch_size;
  }

  // Check URL for ?run=tag
  const params = new URLSearchParams(window.location.search);
  const runTag = params.get('run');
  if (runTag) {
    loadRun(runTag);
  } else {
    // Reset to new simulation state
    activeRunTag = null;
    postReadonly.classList.add('hidden');
    postContent.classList.remove('hidden');
    launchBtn.classList.remove('hidden');
    newSimBtn.classList.add('hidden');
  }

  // Load run history scoped to this community
  loadRunHistory(communityId);
}
```

- [ ] **Step 4: Modify `loadRunHistory` to accept community filter**

```javascript
async function loadRunHistory(communityId) {
  try {
    let url = '/api/runs';
    if (communityId) url += '?community_id=' + communityId;
    const resp = await fetch(url);
    const runs = await resp.json();
    renderRunList(runs);
  } catch(e) {
    console.error('Failed to load run history:', e);
  }
}
```

- [ ] **Step 5: Update launch button to use `activeCommunityId`**

The launch button handler already sends `community_id: activeCommunityId` — verify this still works. The `activeCommunityId` is set by `initSimulateView()`.

- [ ] **Step 6: Update `simulationDone` and `loadRun` for URL-based navigation**

When a run completes or is loaded, update the URL:
```javascript
async function simulationDone(tag) {
  // ...existing code...
  history.replaceState(null, '', '/simulate/' + activeCommunityId + '?run=' + tag);
}
```

- [ ] **Step 7: Verify via browser**

With server running:

1. Use chrome-devtools `navigate_page` to `http://localhost:8000/simulate/1`
2. Use `take_snapshot` to verify: top bar with "← Dashboard" + community badge + persona count, sidebar with config sliders, main panel with launch button + textarea
3. Verify no subreddit input or Generate button in the view
4. Use `click` on "← Dashboard" link → verify URL is `/dashboard`

API verification for scoped runs:
```bash
# Should only return runs for community 1
curl -s "http://localhost:8000/api/runs?community_id=1" | python -c "import sys,json; d=json.load(sys.stdin); print(len(d), 'runs for community 1')"
# Should return all runs
curl -s "http://localhost:8000/api/runs" | python -c "import sys,json; d=json.load(sys.stdin); print(len(d), 'total runs')"
```

- [ ] **Step 8: Commit**

```
git add simulation/static/index.html
git commit -m "feat: refactor simulation view with top bar, scoped history, URL routing"
```

---

## Task 8: Cleanup + final verification

**Files:**
- Delete: `simulation/static/mockup-dashboard.html`, `simulation/static/mockup-add-community.html`, `simulation/static/mockup-simulate.html`
- Modify: `simulation/static/index.html` — remove old header, update page title

- [ ] **Step 1: Update page title**

Change `<title>FlowPulse — Reddit Simulation Lab</title>` to `<title>Reddit Simulation Lab</title>`.

- [ ] **Step 2: Remove FlowPulse default post content**

Replace the FlowPulse example post in the textarea with a generic placeholder:
```
Write your launch post here...
```

- [ ] **Step 3: Delete mockup files**

```bash
rm simulation/static/mockup-dashboard.html
rm simulation/static/mockup-add-community.html
rm simulation/static/mockup-simulate.html
```

- [ ] **Step 4: Run full test suite**

Run: `cd simulation && source .venv/bin/activate && python -m pytest tests/ -v`
Expected: all tests pass

- [ ] **Step 5: Full E2E verification**

```bash
cd simulation && rm -f reddit-sim.db
source .venv/bin/activate && python -m uvicorn server:app --port 8000 &
sleep 2
```

Verify fresh start redirects to setup:
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/product
# Expected: 404
```

Then use chrome-devtools:
1. `navigate_page` to `http://localhost:8000/` → verify URL becomes `/setup`
2. Fill product form via `fill` and `click` submit → verify URL becomes `/dashboard`
3. `take_snapshot` → verify empty communities section
4. `click` "+ Add community" → verify URL is `/communities/new`
5. `fill` subreddit with "r/SaaS", `click` Generate, `wait_for` "personas"
6. `click` Save Community → verify URL is `/dashboard`
7. `take_snapshot` → verify r/SaaS card appears
8. `click` Simulate on r/SaaS card → verify URL starts with `/simulate/`
9. `take_snapshot` → verify top bar, config, launch button, textarea visible

- [ ] **Step 6: Commit**

```
git add -A
git commit -m "chore: cleanup mockups, genericize branding"
```
