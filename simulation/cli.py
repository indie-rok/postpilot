# pyright: reportMissingImports=false, reportAny=false, reportUnusedCallResult=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import argparse
import getpass
import subprocess
import sys
from pathlib import Path


DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "gpt-4o-mini"
MAX_RAW_CONTEXT_BYTES = 16 * 1024


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="post-pilot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init")
    subparsers.add_parser("configure")
    subparsers.add_parser("learn")

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--port", type=int, default=8000)

    return parser.parse_args(argv)


def _prompt_with_default(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def _update_gitignore() -> None:
    candidates = [Path.cwd() / ".gitignore", Path.cwd().parent / ".gitignore"]
    gitignore_path = next((path for path in candidates if path.exists()), candidates[0])

    existing = (
        gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
    )
    lines = existing.splitlines()
    if ".post-pilot/" in lines:
        return

    prefix = "\n" if existing and not existing.endswith("\n") else ""
    gitignore_path.write_text(f"{existing}{prefix}.post-pilot/\n", encoding="utf-8")


def _print_profile_box(profile: dict[str, object]) -> None:
    name = str(profile.get("name", ""))
    audience = str(profile.get("audience", ""))
    problem = str(profile.get("problem", ""))
    features_text = str(profile.get("features", ""))

    lines: list[str] = [
        f"Name: {name}",
        f"Audience: {audience}",
        "Problem:",
        problem,
        "Features:",
    ]

    if features_text.strip():
        lines.extend([line for line in features_text.splitlines() if line.strip()])
    else:
        lines.append("(none)")

    width = max((len(line) for line in lines), default=0)
    print(f"┌{'─' * (width + 2)}┐")
    for line in lines:
        print(f"│ {line.ljust(width)} │")
    print(f"└{'─' * (width + 2)}┘")


def cmd_configure() -> dict[str, str]:
    print("\nStep 1/2: LLM credentials")

    while True:
        llm_api_key = getpass.getpass("LLM API Key: ").strip()
        llm_base_url = _prompt_with_default("Base URL", DEFAULT_BASE_URL)
        llm_model = _prompt_with_default("Model", DEFAULT_MODEL)

        try:
            openai = __import__("openai")
            client = openai.OpenAI(api_key=llm_api_key, base_url=llm_base_url)
            _ = client.chat.completions.create(
                model=llm_model,
                messages=[{"role": "user", "content": "Respond with OK."}],
                temperature=0,
            )
            print("LLM credentials validated.")
            break
        except Exception as exc:
            print(f"LLM validation failed: {exc}")
            skip = input("Skip LLM validation and continue? [y/N]: ").strip().lower()
            if skip in {"y", "yes"}:
                break

    creds: dict[str, str] = {
        "LLM_API_KEY": llm_api_key,
        "LLM_BASE_URL": llm_base_url,
        "LLM_MODEL": llm_model,
    }

    print("\nStep 2/2: Reddit API (optional)")
    configure_reddit = input("Configure Reddit API? [y/N]: ").strip().lower()
    if configure_reddit in {"y", "yes"}:
        reddit_client_id = input("Reddit Client ID: ").strip()
        reddit_client_secret = getpass.getpass("Reddit Client Secret: ").strip()
        try:
            praw = __import__("praw")
            reddit = praw.Reddit(
                client_id=reddit_client_id,
                client_secret=reddit_client_secret,
                user_agent="post-pilot-cli/1.0",
            )
            _ = reddit.auth.scopes()
            print("Reddit credentials validated.")
            creds["REDDIT_CLIENT_ID"] = reddit_client_id
            creds["REDDIT_CLIENT_SECRET"] = reddit_client_secret
        except Exception as exc:
            print(f"Reddit validation failed: {exc}")
            skip = (
                input("Skip Reddit configuration and continue? [y/N]: ").strip().lower()
            )
            if skip not in {"y", "yes"}:
                raise

    return creds


def cmd_learn(api_key: str, base_url: str, model: str) -> dict[str, object]:
    scanner = __import__("scanner")
    profile = scanner.generate_profile(Path.cwd(), api_key, base_url, model)
    _print_profile_box(profile)

    raw_context = scanner.build_llm_context(Path.cwd())
    profile["raw_context"] = raw_context[:MAX_RAW_CONTEXT_BYTES]
    return profile


def cmd_init() -> None:
    print("\n=== PostPilot Setup ===")

    creds = cmd_configure()
    profile = cmd_learn(
        creds["LLM_API_KEY"],
        creds["LLM_BASE_URL"],
        creds["LLM_MODEL"],
    )

    db = __import__("db")
    env_writer = __import__("env_writer")

    project_dir = Path.cwd() / ".post-pilot"
    project_dir.mkdir(parents=True, exist_ok=True)

    db_path = db.get_default_db_path()
    env_path = db.get_env_path()
    profiles_path = (
        Path(__file__).resolve().parent / "profiles" / "r_saas_community.json"
    )

    db.init_db(db_path)
    env_writer.write_env(env_path, creds)
    db.save_product(db_path, profile)
    db.seed_default_community(db_path, str(profiles_path))
    _update_gitignore()

    print("\nSetup complete:")
    print("✓ Database initialized")
    print("✓ Credentials saved")
    print("✓ Product profile generated")
    print("✓ Default community seeded")
    print("✓ .gitignore updated")


def cmd_serve(port: int) -> None:
    db = __import__("db")
    db_path = Path.cwd() / ".post-pilot" / "post-pilot.db"

    if not db_path.exists() or db.get_product(str(db_path)) is None:
        print("No configuration found. Run `npx post-pilot init` first.")
        sys.exit(1)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "server:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ],
        cwd=Path(__file__).resolve().parent,
        check=False,
    )
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    args = parse_args()

    if args.command == "init":
        cmd_init()
        return

    db = __import__("db")
    env_writer = __import__("env_writer")
    project_dir = Path.cwd() / ".post-pilot"
    project_dir.mkdir(parents=True, exist_ok=True)
    db_path = db.get_default_db_path()
    env_path = db.get_env_path()

    if args.command == "configure":
        creds = cmd_configure()
        env_writer.write_env(env_path, creds)
        print(f"Saved credentials to {env_path}")
        return

    if args.command == "learn":
        creds = env_writer.read_env(env_path)
        required = ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"]
        missing = [key for key in required if not creds.get(key)]
        if missing:
            print("Missing LLM credentials. Run `npx post-pilot configure` first.")
            sys.exit(1)

        db.init_db(db_path)
        profile = cmd_learn(
            creds["LLM_API_KEY"],
            creds["LLM_BASE_URL"],
            creds["LLM_MODEL"],
        )
        profile["onboarded"] = 0
        db.save_product(db_path, profile)
        print("Product profile saved.")
        return

    if args.command == "serve":
        cmd_serve(args.port)
        return

    raise RuntimeError(f"Unsupported command: {args.command}")
