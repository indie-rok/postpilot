# CLI Init & npm Wrapper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package Post Pilot as `npx post-pilot` with an interactive `init` wizard that configures credentials, scans the repo, and builds a product profile — all backed by a Python FastAPI server.

**Architecture:** npm package wraps a bundled Python package. Node.js CLI (`bin/post-pilot.js`) manages a venv in `.post-pilot/.venv/`, forwards commands to Python CLI (`python -m post_pilot`). All user data lives under `.post-pilot/` (DB + .env). Web UI gets a one-time Review screen gated by `product.onboarded`.

**Tech Stack:** Node.js (CLI wrapper), Python 3.11+ (FastAPI, SQLite, OASIS), npm (distribution)

**Spec:** `docs/superpowers/specs/2026-03-24-cli-init-npm-wrapper.md`

---

## File Map

### New Files
- `post_pilot/__init__.py` — Package marker
- `post_pilot/__main__.py` — `python -m post_pilot` entry point
- `post_pilot/cli.py` — Command router (init, configure, learn, serve)
- `post_pilot/scanner.py` — Repo file discovery + LLM product profile generation
- `post_pilot/env_writer.py` — Write/read `.post-pilot/.env`
- `post_pilot/pyproject.toml` — Python package metadata
- `bin/post-pilot.js` — Node.js CLI entry point
- `package.json` — npm package config
- `simulation/tests/test_scanner.py` — Scanner unit tests
- `simulation/tests/test_cli.py` — CLI integration tests

### Modified Files
- `simulation/db.py` — Product table schema changes (remove tagline/description/pricing/llm fields, add problem/audience/raw_context/onboarded)
- `simulation/server.py` — Path resolution (cwd-based), remove Setup endpoints, add onboarded endpoint, make LLM config read from .env
- `simulation/static/index.html` — Replace Setup view with Review view, update Settings panel fields
- `simulation/tests/test_db.py` — Update product tests for new schema

### Unchanged
- `simulation/scripts/*` — Simulation scripts stay as-is (moved later during packaging)
- `simulation/config/*` — Config stays as-is
- `simulation/profiles/*` — Profiles stay, r_saas_community.json becomes the bundled default

---

## Task 1: Product Table Schema Migration

**Files:**
- Modify: `simulation/db.py:112-126` (SCHEMA_SQL product table)
- Modify: `simulation/db.py:871-922` (get_product, save_product)
- Modify: `simulation/tests/test_db.py`

- [ ] **Step 1: Write failing tests for new schema**

In `simulation/tests/test_db.py`, update `test_save_and_get_product` and `test_save_product_upserts`:

```python
def test_save_and_get_product(db_path):
    save_product(
        db_path,
        {"name": "TestApp", "problem": "Teams lack visibility", "features": "Analytics, Surveys", "audience": "Remote companies"},
    )
    product = get_product(db_path)
    assert product is not None
    assert product["name"] == "TestApp"
    assert product["problem"] == "Teams lack visibility"
    assert product["features"] == "Analytics, Surveys"
    assert product["audience"] == "Remote companies"
    assert product["onboarded"] == 0


def test_save_product_upserts(db_path):
    save_product(db_path, {"name": "V1", "problem": "Old problem"})
    save_product(db_path, {"name": "V2", "problem": "New problem", "audience": "Devs"})
    product = get_product(db_path)
    assert product["name"] == "V2"
    assert product["problem"] == "New problem"
    assert product["audience"] == "Devs"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest simulation/tests/test_db.py::test_save_and_get_product simulation/tests/test_db.py::test_save_product_upserts -v`
Expected: FAIL (columns don't exist yet)

- [ ] **Step 3: Update product table schema in SCHEMA_SQL**

In `simulation/db.py`, replace the product table definition:

```python
CREATE TABLE IF NOT EXISTS product (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL,
    problem TEXT,
    features TEXT,
    audience TEXT,
    raw_context TEXT,
    onboarded INTEGER DEFAULT 0,
    batch_size INTEGER DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
```

- [ ] **Step 4: Update save_product and get_product**

Replace `save_product` to match new columns:

```python
def save_product(db_path: str, data: dict[str, Any]) -> None:
    conn = get_connection(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO product (id, name, problem, features, audience,
                raw_context, onboarded, batch_size, created_at, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                problem = excluded.problem,
                features = excluded.features,
                audience = excluded.audience,
                raw_context = excluded.raw_context,
                onboarded = excluded.onboarded,
                batch_size = excluded.batch_size,
                updated_at = excluded.updated_at
            """,
            (
                data.get("name", ""),
                data.get("problem"),
                data.get("features"),
                data.get("audience"),
                data.get("raw_context"),
                data.get("onboarded", 0),
                data.get("batch_size", 0),
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest simulation/tests/test_db.py -v`
Expected: ALL PASS

- [ ] **Step 6: Delete old DB and re-test full suite**

The existing `simulation/reddit-sim.db` has the old schema. Delete it so `init_db` recreates with new schema.

Run: `rm -f simulation/reddit-sim.db && python -m pytest simulation/tests/ -v`
Expected: ALL PASS (65 tests). Some tests may need minor fixes if they reference old product columns.

- [ ] **Step 7: Commit**

```bash
git add simulation/db.py simulation/tests/test_db.py
git commit -m "refactor: simplify product table schema — remove tagline/description/pricing/llm, add problem/audience/raw_context/onboarded"
```

---

## Task 2: Path Resolution — cwd-Based DB and .env

**Files:**
- Modify: `simulation/db.py` (add `get_project_dir()` helper)
- Modify: `simulation/server.py:61-74` (path constants, dotenv loading)

- [ ] **Step 1: Add `get_project_dir()` to db.py**

At the top of `simulation/db.py`, add:

```python
from pathlib import Path

def get_project_dir() -> Path:
    """Return the .post-pilot directory under cwd. Create if needed."""
    d = Path.cwd() / ".post-pilot"
    d.mkdir(exist_ok=True)
    return d

def get_default_db_path() -> str:
    return str(get_project_dir() / "post-pilot.db")

def get_env_path() -> Path:
    return get_project_dir() / ".env"
```

- [ ] **Step 2: Update server.py path resolution**

Replace the hardcoded `APP_DB` and dotenv loading:

```python
from db import get_default_db_path, get_env_path

# Replace: APP_DB = str(BASE_DIR / "reddit-sim.db")
APP_DB = get_default_db_path()

# Replace: _ = load_dotenv(BASE_DIR / ".env")
_ = load_dotenv(get_env_path())
```

Keep `BASE_DIR`, `STATIC_DIR`, `PROFILES_DIR` pointing to the package directory (they reference bundled assets, not user data).

- [ ] **Step 3: Test server starts with new paths**

Run: `mkdir -p .post-pilot && python -m pytest simulation/tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add simulation/db.py simulation/server.py
git commit -m "refactor: resolve DB and .env from cwd/.post-pilot/ instead of package directory"
```

---

## Task 3: .env Writer Module

**Files:**
- Create: `simulation/env_writer.py`
- Create: `simulation/tests/test_env_writer.py`

- [ ] **Step 1: Write tests for env_writer**

```python
# simulation/tests/test_env_writer.py
import os
from pathlib import Path
from env_writer import write_env, read_env

def test_write_and_read_env(tmp_path):
    env_path = tmp_path / ".env"
    creds = {
        "LLM_API_KEY": "sk-test",
        "LLM_BASE_URL": "http://localhost:8000/v1",
        "LLM_MODEL": "gpt-4o-mini",
    }
    write_env(env_path, creds)
    assert env_path.exists()
    result = read_env(env_path)
    assert result["LLM_API_KEY"] == "sk-test"
    assert result["LLM_BASE_URL"] == "http://localhost:8000/v1"

def test_write_env_overwrites(tmp_path):
    env_path = tmp_path / ".env"
    write_env(env_path, {"LLM_API_KEY": "old"})
    write_env(env_path, {"LLM_API_KEY": "new"})
    result = read_env(env_path)
    assert result["LLM_API_KEY"] == "new"

def test_read_env_missing_file(tmp_path):
    result = read_env(tmp_path / "nonexistent")
    assert result == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest simulation/tests/test_env_writer.py -v`
Expected: FAIL (module doesn't exist)

- [ ] **Step 3: Implement env_writer.py**

```python
# simulation/env_writer.py
from pathlib import Path

def write_env(path: Path, creds: dict[str, str]) -> None:
    lines = []
    for key, value in creds.items():
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n")

def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest simulation/tests/test_env_writer.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add simulation/env_writer.py simulation/tests/test_env_writer.py
git commit -m "feat: add env_writer module for .post-pilot/.env credential management"
```

---

## Task 4: Repo Scanner Module

**Files:**
- Create: `simulation/scanner.py`
- Create: `simulation/tests/test_scanner.py`

- [ ] **Step 1: Write tests for file discovery**

```python
# simulation/tests/test_scanner.py
import json
from pathlib import Path
from scanner import discover_files, build_llm_context

def test_discover_finds_readme(tmp_path):
    (tmp_path / "README.md").write_text("# My App\nA cool thing")
    files = discover_files(tmp_path)
    assert any(f.name == "README.md" for f in files)

def test_discover_skips_node_modules(tmp_path):
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("module.exports = {}")
    (tmp_path / "README.md").write_text("# App")
    files = discover_files(tmp_path)
    paths = [str(f) for f in files]
    assert not any("node_modules" in p for p in paths)

def test_discover_skips_large_files(tmp_path):
    (tmp_path / "big.txt").write_text("x" * 60_000)
    (tmp_path / "small.txt").write_text("hello")
    files = discover_files(tmp_path)
    names = [f.name for f in files]
    assert "small.txt" in names
    assert "big.txt" not in names

def test_build_llm_context_truncates(tmp_path):
    (tmp_path / "README.md").write_text("A" * 10_000)
    context = build_llm_context(tmp_path)
    assert len(context) <= 16_500  # 16KB + some header overhead
    assert "README.md" in context
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest simulation/tests/test_scanner.py -v`
Expected: FAIL

- [ ] **Step 3: Implement scanner.py — file discovery**

```python
# simulation/scanner.py
from pathlib import Path

SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", ".next", "__pycache__",
    ".venv", "venv", "vendor", ".post-pilot", ".tox", ".mypy_cache",
    ".pytest_cache", "coverage", ".nyc_output",
}

SCAN_NAMES = {
    "README.md", "README.rst", "README.txt",
    "package.json", "pyproject.toml", "Cargo.toml", "go.mod",
    "composer.json", "Gemfile",
}

MAX_FILE_SIZE = 50_000  # 50KB
MAX_INDIVIDUAL = 4_000  # 4KB per file
MAX_TOTAL = 16_000      # 16KB total context

def discover_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for item in sorted(root.iterdir()):
        if item.name.startswith(".") and item.name not in (".env.example",):
            continue
        if item.is_dir():
            if item.name in SKIP_DIRS:
                continue
            if item.name == "docs":
                for doc in sorted(item.iterdir())[:5]:
                    if doc.is_file() and doc.stat().st_size <= MAX_FILE_SIZE:
                        found.append(doc)
            continue
        if item.is_file():
            if item.stat().st_size > MAX_FILE_SIZE:
                continue
            if item.name in SCAN_NAMES:
                found.append(item)
    return found

def _read_truncated(path: Path) -> str:
    try:
        text = path.read_text(errors="replace")
        return text[:MAX_INDIVIDUAL]
    except Exception:
        return ""

def _build_tree(root: Path, depth: int = 0, max_depth: int = 2) -> str:
    if depth > max_depth:
        return ""
    lines: list[str] = []
    try:
        entries = sorted(root.iterdir())
    except PermissionError:
        return ""
    for item in entries:
        if item.name.startswith(".") or item.name in SKIP_DIRS:
            continue
        prefix = "  " * depth
        if item.is_dir():
            lines.append(f"{prefix}{item.name}/")
            lines.append(_build_tree(item, depth + 1, max_depth))
        else:
            lines.append(f"{prefix}{item.name}")
    return "\n".join(lines)

def build_llm_context(root: Path) -> str:
    files = discover_files(root)
    parts: list[str] = []
    total = 0

    # File tree first
    tree = _build_tree(root)
    tree_section = f"## File Structure\n```\n{tree}\n```\n"
    parts.append(tree_section)
    total += len(tree_section)

    # File contents
    for f in files:
        if total >= MAX_TOTAL:
            break
        content = _read_truncated(f)
        rel = f.relative_to(root)
        section = f"## {rel}\n```\n{content}\n```\n"
        if total + len(section) > MAX_TOTAL:
            remaining = MAX_TOTAL - total
            section = section[:remaining]
        parts.append(section)
        total += len(section)

    return "\n".join(parts)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest simulation/tests/test_scanner.py -v`
Expected: ALL PASS

- [ ] **Step 5: Add LLM profile generation function**

Add to `simulation/scanner.py`:

```python
import json
import os
from openai import OpenAI

PROFILE_PROMPT = """You are analyzing a software project. Based on the files below, generate a product profile.

Return ONLY valid JSON with exactly these 4 fields:
{
  "name": "Product name",
  "problem": "One condensed paragraph about the problem it solves. No marketing language.",
  "features": "3-6 bullet points, each under 10 words. Separated by newlines.",
  "audience": "One sentence: who is this for?"
}

Be extremely concise. No filler. Write like a developer explaining their product to a friend.

---
PROJECT FILES:
"""

def generate_profile(root: Path, api_key: str, base_url: str, model: str) -> dict[str, str]:
    context = build_llm_context(root)
    client = OpenAI(api_key=api_key, base_url=base_url)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": PROFILE_PROMPT + context}],
        temperature=0.3,
    )
    text = resp.choices[0].message.content or "{}"
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())
```

- [ ] **Step 6: Commit**

```bash
git add simulation/scanner.py simulation/tests/test_scanner.py
git commit -m "feat: add repo scanner with file discovery, context building, and LLM profile generation"
```

---

## Task 5: Python CLI — Command Router

**Files:**
- Create: `simulation/cli.py`
- Create: `simulation/tests/test_cli.py`

- [ ] **Step 1: Write test for CLI argument parsing**

```python
# simulation/tests/test_cli.py
from cli import parse_args

def test_parse_init():
    args = parse_args(["init"])
    assert args.command == "init"

def test_parse_serve_with_port():
    args = parse_args(["serve", "--port", "3000"])
    assert args.command == "serve"
    assert args.port == 3000

def test_parse_configure():
    args = parse_args(["configure"])
    assert args.command == "configure"

def test_parse_learn():
    args = parse_args(["learn"])
    assert args.command == "learn"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest simulation/tests/test_cli.py -v`
Expected: FAIL

- [ ] **Step 3: Implement cli.py — argument parser + command stubs**

```python
# simulation/cli.py
import argparse
import sys
from pathlib import Path

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="post-pilot", description="Post Pilot — test your post before you post")
    sub = parser.add_subparsers(dest="command")
    sub.required = True

    sub.add_parser("init", help="Full setup wizard")
    sub.add_parser("configure", help="Set up LLM and Reddit API credentials")
    sub.add_parser("learn", help="Scan repo and generate product profile")

    serve_p = sub.add_parser("serve", help="Launch web UI")
    serve_p.add_argument("--port", type=int, default=8000)

    return parser.parse_args(argv)


def cmd_configure() -> dict[str, str]:
    """Collect LLM + Reddit credentials interactively. Return dict of env vars."""
    import getpass
    print("\n  Step 1: LLM Configuration")
    print("  Your LLM powers product analysis and community simulation.\n")

    api_key = getpass.getpass("  API Key: ")
    base_url = input("  Base URL [https://openrouter.ai/api/v1]: ").strip()
    if not base_url:
        base_url = "https://openrouter.ai/api/v1"
    model = input("  Model [gpt-4o-mini]: ").strip()
    if not model:
        model = "gpt-4o-mini"

    # Validate LLM
    print("\n  Testing connection...", end=" ", flush=True)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with OK"}],
            max_tokens=5,
        )
        print("✓ Connected\n")
    except Exception as e:
        print(f"✗ Failed: {e}")
        skip = input("  Skip validation and continue? [y/N]: ").strip().lower()
        if skip != "y":
            sys.exit(1)

    creds: dict[str, str] = {
        "LLM_API_KEY": api_key,
        "LLM_BASE_URL": base_url,
        "LLM_MODEL": model,
    }

    # Reddit API (optional)
    print("  Step 2: Reddit API (optional)")
    print("  Used to generate community personas from real subreddits.")
    print("  You can skip this and use pre-built communities.\n")
    configure_reddit = input("  Configure Reddit API? [y/N]: ").strip().lower()
    if configure_reddit == "y":
        client_id = input("  Client ID: ").strip()
        client_secret = getpass.getpass("  Client Secret: ")
        print("\n  Testing connection...", end=" ", flush=True)
        try:
            import praw
            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent="post-pilot/1.0",
            )
            _ = reddit.subreddit("test").title
            print("✓ Connected\n")
        except Exception as e:
            print(f"✗ Failed: {e}\n")
        creds["REDDIT_CLIENT_ID"] = client_id
        creds["REDDIT_CLIENT_SECRET"] = client_secret
    else:
        print("  ✓ Skipped\n")

    return creds


def cmd_learn(api_key: str, base_url: str, model: str) -> dict[str, str]:
    """Scan repo and generate product profile. Returns profile dict."""
    from scanner import generate_profile, build_llm_context

    root = Path.cwd()
    print("\n  Step 3: Product Discovery")
    print(f"  Scanning {root.name}/...\n")

    profile = generate_profile(root, api_key, base_url, model)

    # Display summary
    print("  ┌─────────────────────────────────────────┐")
    print(f"  │  Name:     {profile.get('name', '?'):<30}│")
    print(f"  │  Problem:  {profile.get('problem', '?')[:30]:<30}│")
    print(f"  │  Audience: {profile.get('audience', '?')[:30]:<30}│")
    print("  └─────────────────────────────────────────┘")

    # Store raw context
    profile["raw_context"] = build_llm_context(root)[:16_000]

    return profile


def cmd_init() -> None:
    """Full init wizard: configure + learn + finalize."""
    from db import get_default_db_path, get_env_path, init_db, save_product, seed_default_community
    from env_writer import write_env

    print("\n  PostPilot Setup")
    print("  ───────────────\n")

    # Step 1-2: Credentials
    creds = cmd_configure()

    # Step 3: Scan
    profile = cmd_learn(creds["LLM_API_KEY"], creds["LLM_BASE_URL"], creds["LLM_MODEL"])

    # Finalize
    project_dir = Path.cwd() / ".post-pilot"
    project_dir.mkdir(exist_ok=True)

    db_path = get_default_db_path()
    init_db(db_path)
    write_env(get_env_path(), creds)
    save_product(db_path, profile)
    seed_default_community(db_path)

    # .gitignore
    gitignore = Path.cwd() / ".gitignore"
    marker = ".post-pilot/"
    if gitignore.exists():
        content = gitignore.read_text()
        if marker not in content:
            with open(gitignore, "a") as f:
                f.write(f"\n# Post Pilot\n{marker}\n")
    else:
        gitignore.write_text(f"# Post Pilot\n{marker}\n")

    print("  ✓ Credentials saved to .post-pilot/.env")
    print("  ✓ Product profile saved to database")
    print(f"  ✓ Database initialized at {db_path}")
    print("  ✓ Default community (r/SaaS) seeded")
    print("  ✓ Added .post-pilot/ to .gitignore")
    print()
    print("  Next: npx post-pilot serve")
    print("  Your product profile will be shown for review on first launch.")


def cmd_serve(port: int) -> None:
    """Start FastAPI server."""
    from db import get_default_db_path, get_product
    import subprocess

    db_path = get_default_db_path()
    if not Path(db_path).exists() or get_product(db_path) is None:
        print("No configuration found. Run `npx post-pilot init` first.")
        sys.exit(1)

    subprocess.run(
        [sys.executable, "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", str(port)],
        cwd=Path(__file__).resolve().parent,
    )


def main() -> None:
    args = parse_args()
    if args.command == "init":
        cmd_init()
    elif args.command == "configure":
        from db import get_env_path
        from env_writer import write_env
        creds = cmd_configure()
        project_dir = Path.cwd() / ".post-pilot"
        project_dir.mkdir(exist_ok=True)
        write_env(get_env_path(), creds)
        print("  ✓ Credentials saved to .post-pilot/.env")
    elif args.command == "learn":
        from db import get_default_db_path, get_env_path, get_product, save_product
        from env_writer import read_env
        env = read_env(get_env_path())
        if not env.get("LLM_API_KEY"):
            print("No LLM credentials found. Run `npx post-pilot configure` first.")
            sys.exit(1)
        db_path = get_default_db_path()
        if not Path(db_path).exists():
            print("No database found. Run `npx post-pilot init` first.")
            sys.exit(1)
        profile = cmd_learn(env["LLM_API_KEY"], env.get("LLM_BASE_URL", ""), env.get("LLM_MODEL", ""))
        profile["onboarded"] = 0  # Reset so web Review screen shows again
        save_product(db_path, profile)
        print("  ✓ Product profile updated")
    elif args.command == "serve":
        cmd_serve(args.port)
```

- [ ] **Step 4: Create `__main__.py`**

```python
# simulation/__main__.py (later becomes post_pilot/__main__.py)
from cli import main
main()
```

- [ ] **Step 5: Run CLI parser tests**

Run: `python -m pytest simulation/tests/test_cli.py -v`
Expected: ALL PASS

- [ ] **Step 6: Manual smoke test of init (dry run)**

Run from repo root: `cd simulation && python -c "from cli import parse_args; print(parse_args(['init']))"`
Expected: `Namespace(command='init')`

- [ ] **Step 7: Commit**

```bash
git add simulation/cli.py simulation/__main__.py simulation/tests/test_cli.py
git commit -m "feat: add CLI command router with init, configure, learn, serve commands"
```

---

## Task 6: Web UI — Review View + Settings Panel Update

**Files:**
- Modify: `simulation/static/index.html` (Setup view HTML, Settings panel HTML, JS routing)
- Modify: `simulation/server.py` (add onboarded endpoint, update product endpoints)

- [ ] **Step 1: Add onboarded API endpoint**

In `simulation/server.py`, add:

```python
@app.post("/api/product/onboard")
async def onboard_product() -> dict[str, str]:
    product = get_product(APP_DB)
    if not product:
        raise HTTPException(status_code=404, detail="No product found")
    save_product(APP_DB, {**product, "onboarded": 1})
    return {"status": "ok"}
```

- [ ] **Step 2: Replace Setup view HTML with Review view**

In `simulation/static/index.html`, replace the `view-setup` div contents:

```html
<div id="view-setup" class="view">
<div style="max-width:700px;margin:60px auto;padding:0 24px;">
  <div style="text-align:center;margin-bottom:32px;">
    <div class="app-wordmark" style="font-size:32px;display:inline;">Post<span>Pilot</span></div>
    <div style="color:var(--muted);font-size:14px;margin-top:6px;">Test your post before you post</div>
  </div>
  <p style="color:var(--muted);font-size:14px;margin-bottom:24px;">Here's what we learned about your product. Make any edits before your first simulation.</p>

  <div class="form-group">
    <div class="small-label">Product Name</div>
    <input type="text" id="review-name">
  </div>
  <div class="form-group">
    <div class="small-label">What problem does it solve?</div>
    <textarea id="review-problem" style="height:100px;"></textarea>
  </div>
  <div class="form-group">
    <div class="small-label">Key Features</div>
    <textarea id="review-features" style="height:80px;"></textarea>
  </div>
  <div class="form-group">
    <div class="small-label">Who is this for?</div>
    <input type="text" id="review-audience">
  </div>

  <div style="margin-top:20px;padding:16px;background:var(--card);border-radius:8px;border:1px solid var(--border);">
    <div class="small-label" style="margin-bottom:8px;">LLM Configuration</div>
    <div id="review-llm-info" style="color:var(--muted);font-size:13px;"></div>
    <div style="color:var(--muted);font-size:12px;margin-top:4px;">Edit in <code>.post-pilot/.env</code> or run <code>npx post-pilot configure</code></div>
  </div>

  <button type="button" id="review-confirm-btn" style="margin-top:20px;">Looks good →</button>
</div>
</div>
```

- [ ] **Step 3: Update JS routing — `checkProductAndRoute` checks onboarded**

```javascript
async function checkProductAndRoute() {
    try {
        const resp = await fetch('/api/product');
        if (!resp.ok) {
            // No product = init not run. Show message.
            document.getElementById('app').innerHTML = `
                <div style="text-align:center;margin-top:100px;color:var(--muted);">
                    <div class="app-wordmark" style="font-size:32px;display:inline;">Post<span>Pilot</span></div>
                    <p style="margin-top:16px;">Run <code>npx post-pilot init</code> in your terminal to get started.</p>
                </div>`;
            return;
        }
        const product = await resp.json();
        if (!product.onboarded) {
            navigateTo('/setup');  // Shows Review view
        } else {
            navigateTo('/dashboard');
        }
    } catch (e) {
        navigateTo('/setup');
    }
}
```

- [ ] **Step 4: Update `initSetup()` → `initReview()` — populate Review form**

```javascript
async function initSetup() {
    // Now serves as Review view
    try {
        const resp = await fetch('/api/product');
        if (!resp.ok) return;
        const product = await resp.json();
        document.getElementById('review-name').value = product.name || '';
        document.getElementById('review-problem').value = product.problem || '';
        document.getElementById('review-features').value = product.features || '';
        document.getElementById('review-audience').value = product.audience || '';

        // Show LLM info (read from env via API)
        const envResp = await fetch('/api/llm-config');
        if (envResp.ok) {
            const env = await envResp.json();
            document.getElementById('review-llm-info').textContent =
                `Model: ${env.model || '—'}  •  Endpoint: ${env.base_url || '—'}`;
        }
    } catch (e) { console.error(e); }
}
```

- [ ] **Step 5: Add Review confirm button handler**

```javascript
document.getElementById('review-confirm-btn').addEventListener('click', async () => {
    const btn = document.getElementById('review-confirm-btn');
    btn.disabled = true;
    btn.textContent = 'Saving...';
    try {
        // Save any edits
        await fetch('/api/product', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: document.getElementById('review-name').value,
                problem: document.getElementById('review-problem').value,
                features: document.getElementById('review-features').value,
                audience: document.getElementById('review-audience').value,
            })
        });
        // Mark onboarded
        await fetch('/api/product/onboard', { method: 'POST' });
        navigateTo('/dashboard');
    } catch (e) {
        btn.disabled = false;
        btn.textContent = 'Looks good →';
    }
});
```

- [ ] **Step 6: Add `/api/llm-config` endpoint (read-only, no key exposed)**

In `simulation/server.py`:

```python
@app.get("/api/llm-config")
async def get_llm_config() -> dict[str, str]:
    return {
        "model": os.getenv("LLM_MODEL", ""),
        "base_url": os.getenv("LLM_BASE_URL", ""),
    }
```

- [ ] **Step 7: Update Settings panel — new fields, read-only LLM**

Replace Settings panel HTML with:

```html
<div id="settings-panel" class="settings-panel">
  <button class="settings-close" onclick="document.getElementById('settings-panel').classList.remove('open')">&times;</button>
  <h2 style="margin-top:0;">Settings</h2>

  <div class="form-group" style="margin-top:24px;">
    <div class="small-label">Product Name</div>
    <input type="text" id="dash-setup-name">
  </div>
  <div class="form-group">
    <div class="small-label">What problem does it solve?</div>
    <textarea id="dash-setup-problem" style="height:100px;"></textarea>
  </div>
  <div class="form-group">
    <div class="small-label">Key Features</div>
    <textarea id="dash-setup-features" style="height:80px;"></textarea>
  </div>
  <div class="form-group">
    <div class="small-label">Who is this for?</div>
    <input type="text" id="dash-setup-audience">
  </div>

  <h2 style="margin-top:24px;">LLM Configuration</h2>
  <div style="color:var(--muted);font-size:13px;" id="settings-llm-info">Loading...</div>
  <div style="color:var(--muted);font-size:12px;margin-top:4px;">Edit in <code>.post-pilot/.env</code> or run <code>npx post-pilot configure</code></div>

  <button type="button" id="dash-save-btn" style="margin-top:16px;">Save Settings</button>
</div>
```

- [ ] **Step 8: Update Settings JS — load/save new fields**

Update the Settings panel load/save handlers to use `problem`, `features`, `audience` instead of `tagline`, `description`, `pricing`, `target_audience`, `llm_model`, `llm_base_url`, `llm_api_key`.

- [ ] **Step 9: Update server.py ProductRequest model**

```python
class ProductRequest(BaseModel):
    name: str = ""
    problem: str | None = None
    features: str | None = None
    audience: str | None = None
    raw_context: str | None = None
    onboarded: int = Field(default=0)
    batch_size: int = Field(default=0)
```

- [ ] **Step 10: Remove `/api/company-md` endpoint**

Delete the `company_md` endpoint from server.py — no longer needed.

- [ ] **Step 11: Manual test — start server, verify Review screen**

Run server, open browser, verify Review screen shows with product data and "Looks good →" button works.

- [ ] **Step 12: Commit**

```bash
git add simulation/static/index.html simulation/server.py
git commit -m "feat: replace Setup view with one-time Review screen, update Settings panel to new product fields"
```

---

## Task 7: npm Wrapper

**Files:**
- Create: `package.json`
- Create: `bin/post-pilot.js`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "post-pilot",
  "version": "0.1.0",
  "description": "Test your Reddit launch post against AI community personas before posting",
  "bin": {
    "post-pilot": "./bin/post-pilot.js"
  },
  "files": [
    "bin/",
    "simulation/"
  ],
  "keywords": ["reddit", "simulation", "launch", "saas", "ai"],
  "license": "MIT"
}
```

- [ ] **Step 2: Create bin/post-pilot.js**

```javascript
#!/usr/bin/env node

const { execSync, spawn } = require('child_process');
const { existsSync, mkdirSync } = require('fs');
const { join, resolve } = require('path');

const PROJECT_DIR = join(process.cwd(), '.post-pilot');
const VENV_DIR = join(PROJECT_DIR, '.venv');
const PYTHON_PKG_DIR = join(__dirname, '..', 'simulation');

// Platform-aware paths
const isWin = process.platform === 'win32';
const VENV_PYTHON = isWin
  ? join(VENV_DIR, 'Scripts', 'python.exe')
  : join(VENV_DIR, 'bin', 'python');
const VENV_PIP = isWin
  ? join(VENV_DIR, 'Scripts', 'pip')
  : join(VENV_DIR, 'bin', 'pip');

function findPython() {
  const candidates = isWin ? ['python', 'python3'] : ['python3', 'python'];
  for (const cmd of candidates) {
    try {
      const version = execSync(`${cmd} --version 2>&1`, { encoding: 'utf8' }).trim();
      const match = version.match(/Python (\d+)\.(\d+)/);
      if (match && (parseInt(match[1]) > 3 || (parseInt(match[1]) === 3 && parseInt(match[2]) >= 11))) {
        return cmd;
      }
    } catch {}
  }
  return null;
}

function ensureVenv(pythonCmd) {
  if (!existsSync(VENV_PYTHON)) {
    console.log('  Setting up Python environment...');
    mkdirSync(PROJECT_DIR, { recursive: true });
    execSync(`${pythonCmd} -m venv "${VENV_DIR}"`, { stdio: 'inherit' });
    execSync(`"${VENV_PIP}" install -q "${PYTHON_PKG_DIR}"`, { stdio: 'inherit' });
    console.log('  ✓ Python environment ready\n');
  }
}

// Main
const args = process.argv.slice(2);
if (args.length === 0 || args[0] === '--help' || args[0] === '-h') {
  console.log(`
  Post Pilot — test your post before you post

  Commands:
    init        Full setup wizard
    configure   Set up LLM and Reddit API credentials
    learn       Scan repo and generate product profile
    serve       Launch web UI (default port 8000)

  Usage:
    npx post-pilot init
    npx post-pilot serve --port 3000
`);
  process.exit(0);
}

const python = findPython();
if (!python) {
  console.error('Python 3.11+ is required. Install from https://python.org');
  process.exit(1);
}

ensureVenv(python);

// Forward to Python CLI
const child = spawn(VENV_PYTHON, ['-m', 'cli', ...args], {
  cwd: PYTHON_PKG_DIR,
  stdio: 'inherit',
  env: { ...process.env, PYTHONPATH: PYTHON_PKG_DIR },
});

child.on('exit', (code) => process.exit(code || 0));
```

- [ ] **Step 3: Make post-pilot.js executable**

Run: `chmod +x bin/post-pilot.js`

- [ ] **Step 4: Smoke test — run locally**

Run: `node bin/post-pilot.js --help`
Expected: Shows help text with commands.

Run: `node bin/post-pilot.js serve` (should fail with "No configuration found" if no .post-pilot/ exists)

- [ ] **Step 5: Commit**

```bash
git add package.json bin/post-pilot.js
git commit -m "feat: add npm wrapper — npx post-pilot CLI that manages Python venv"
```

---

## Task 8: Update Existing Tests + Full Verification

**Files:**
- Modify: `simulation/tests/test_db.py` (fix any remaining references to old product columns)
- Modify: `simulation/tests/test_scorecard.py` (if it references product fields)

- [ ] **Step 1: Grep for old product column references in tests**

Search all test files for: `tagline`, `description`, `pricing`, `target_audience`, `llm_model`, `llm_base_url`, `llm_api_key`.
Fix any references to use new column names.

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest simulation/tests/ -v`
Expected: ALL PASS

- [ ] **Step 3: Run LSP diagnostics**

Check `simulation/db.py`, `simulation/server.py`, `simulation/cli.py`, `simulation/scanner.py`, `simulation/env_writer.py` for type errors.

- [ ] **Step 4: Manual end-to-end test**

1. Delete `.post-pilot/` if it exists
2. Run `node bin/post-pilot.js init` — go through wizard
3. Run `node bin/post-pilot.js serve` — verify web UI opens
4. Verify Review screen shows with product profile
5. Click "Looks good →" — verify redirect to Dashboard
6. Open Settings — verify new fields, read-only LLM section
7. Run a simulation — verify it works end-to-end

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: Post Pilot CLI init + npm wrapper — complete onboarding flow"
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Product table schema migration | db.py, test_db.py |
| 2 | cwd-based path resolution | db.py, server.py |
| 3 | .env writer module | env_writer.py, test_env_writer.py |
| 4 | Repo scanner module | scanner.py, test_scanner.py |
| 5 | CLI command router (init/configure/learn/serve) | cli.py, __main__.py, test_cli.py |
| 6 | Web UI: Review view + Settings update | index.html, server.py |
| 7 | npm wrapper | package.json, bin/post-pilot.js |
| 8 | Test fixup + full verification | all test files |
