# pyright: reportMissingImports=false, reportAny=false, reportUnusedCallResult=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import argparse
import getpass
import os
import subprocess
import sys
import threading
from pathlib import Path


DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "gpt-4o-mini"
MAX_RAW_CONTEXT_BYTES = 16 * 1024


def _user_cwd() -> Path:
    env_dir = os.environ.get("POST_PILOT_PROJECT_DIR")
    return Path(env_dir) if env_dir else Path.cwd()


_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_CLR = "\x1b[2K\r"
_GREEN = "\x1b[32m"
_RED = "\x1b[31m"
_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"


class Spinner:
    """Thread-based terminal spinner."""

    def __init__(self, message: str) -> None:
        self.message = message
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> "Spinner":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        i = 0
        while not self._stop.is_set():
            frame = _SPINNER_FRAMES[i % len(_SPINNER_FRAMES)]
            sys.stdout.write(f"{_CLR}  {frame} {self.message}")
            sys.stdout.flush()
            i += 1
            self._stop.wait(0.08)

    def stop(self, final: str | None = None) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        sys.stdout.write(f"{_CLR}  {_GREEN}✓{_RESET} {final or self.message}\n")
        sys.stdout.flush()

    def fail(self, final: str | None = None) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        sys.stdout.write(f"{_CLR}  {_RED}✗{_RESET} {final or self.message}\n")
        sys.stdout.flush()


def _read_masked(prompt: str) -> str:
    """Read a line of input, echoing ``*`` for each character."""
    if not sys.stdin.isatty():
        return getpass.getpass(prompt)

    if sys.platform == "win32":
        import msvcrt

        sys.stdout.write(prompt)
        sys.stdout.flush()
        chars: list[str] = []
        while True:
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                sys.stdout.write("\n")
                break
            elif ch == "\x08":
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
            elif ch == "\x03":
                raise KeyboardInterrupt
            else:
                chars.append(ch)
                sys.stdout.write("*")
            sys.stdout.flush()
        return "".join(chars)

    import termios
    import tty

    sys.stdout.write(prompt)
    sys.stdout.flush()
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        chars = []
        while True:
            ch = sys.stdin.read(1)
            if not ch:
                sys.stdout.write("\n")
                raise EOFError
            if ch in ("\r", "\n"):
                sys.stdout.write("\n")
                break
            elif ch in ("\x7f", "\x08"):
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
            elif ch == "\x03":
                raise KeyboardInterrupt
            elif ch == "\x04":
                sys.stdout.write("\n")
                raise EOFError
            else:
                chars.append(ch)
                sys.stdout.write("*")
            sys.stdout.flush()
        return "".join(chars)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


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
    project = _user_cwd()
    candidates = [project / ".gitignore", project.parent / ".gitignore"]
    gitignore_path = next((path for path in candidates if path.exists()), candidates[0])

    existing = (
        gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
    )
    lines = existing.splitlines()
    if ".post-pilot/" in lines:
        return

    prefix = "\n" if existing and not existing.endswith("\n") else ""
    gitignore_path.write_text(f"{existing}{prefix}.post-pilot/\n", encoding="utf-8")


def _print_profile(profile: dict[str, object]) -> None:
    name = str(profile.get("name", ""))
    audience = str(profile.get("audience", ""))
    problem = str(profile.get("problem", ""))
    features_text = str(profile.get("features", ""))

    pad = 11
    print()
    print(f"  {_BOLD}Product Profile{_RESET}")
    print()
    print("  " + "Name".ljust(pad) + name)
    print("  " + "Audience".ljust(pad) + audience)

    problem_lines = [l.strip() for l in problem.splitlines() if l.strip()]
    if problem_lines:
        print("  " + "Problem".ljust(pad) + problem_lines[0])
        for extra in problem_lines[1:]:
            print("  " + "".ljust(pad) + extra)
    else:
        print("  " + "Problem".ljust(pad) + "(none)")

    feature_items: list[str] = []
    if features_text.strip():
        for line in features_text.splitlines():
            stripped = line.strip()
            if stripped:
                if stripped[0] in "-*•":
                    stripped = stripped[1:].strip()
                feature_items.append(stripped)

    if feature_items:
        print()
        print("  Features")
        for item in feature_items:
            print(f"    · {item}")

    print()


def cmd_configure() -> dict[str, str]:
    print("\n  Step 1/2 · LLM credentials\n")

    while True:
        llm_base_url = _prompt_with_default("  Base URL", DEFAULT_BASE_URL)
        llm_model = _prompt_with_default("  Model", DEFAULT_MODEL)
        llm_api_key = _read_masked("  API Key: ").strip()

        sp = Spinner("Validating LLM credentials...").start()
        try:
            openai = __import__("openai")
            client = openai.OpenAI(api_key=llm_api_key, base_url=llm_base_url)
            _ = client.chat.completions.create(
                model=llm_model,
                messages=[{"role": "user", "content": "Respond with OK."}],
                temperature=0,
            )
            sp.stop("LLM credentials validated")
            break
        except Exception as exc:
            sp.fail("LLM validation failed")
            print(f"    {exc}")
            skip = input("  Skip validation and continue? [y/N]: ").strip().lower()
            if skip in {"y", "yes"}:
                break

    creds: dict[str, str] = {
        "LLM_API_KEY": llm_api_key,
        "LLM_BASE_URL": llm_base_url,
        "LLM_MODEL": llm_model,
    }

    print("\n  Step 2/2 · Reddit API (optional)")
    print(f"  {_BOLD}({_RESET}Get credentials at {_BOLD}https://www.reddit.com/prefs/apps{_RESET} → create app → select \"script\"{_BOLD}){_RESET}\n")
    configure_reddit = input("  Configure Reddit API? [y/N]: ").strip().lower()
    if configure_reddit in {"y", "yes"}:
        reddit_client_id = input("  Reddit Client ID: ").strip()
        reddit_client_secret = _read_masked("  Reddit Client Secret: ").strip()

        sp = Spinner("Validating Reddit credentials...").start()
        try:
            praw = __import__("praw")
            reddit = praw.Reddit(
                client_id=reddit_client_id,
                client_secret=reddit_client_secret,
                user_agent="post-pilot-cli/1.0",
            )
            _ = reddit.auth.scopes()
            sp.stop("Reddit credentials validated")
            creds["REDDIT_CLIENT_ID"] = reddit_client_id
            creds["REDDIT_CLIENT_SECRET"] = reddit_client_secret
        except Exception as exc:
            sp.fail("Reddit validation failed")
            print(f"    {exc}")
            skip = input("  Skip Reddit and continue? [y/N]: ").strip().lower()
            if skip not in {"y", "yes"}:
                raise

    return creds


def cmd_learn(api_key: str, base_url: str, model: str) -> dict[str, object]:
    scanner = __import__("scanner")
    project = _user_cwd()
    profile = scanner.generate_profile(project, api_key, base_url, model)

    raw_context = scanner.build_llm_context(project)
    profile["raw_context"] = raw_context[:MAX_RAW_CONTEXT_BYTES]
    return profile


def cmd_init() -> None:
    print("\n  ══ PostPilot Setup ══")

    creds = cmd_configure()

    sp = Spinner("Learning about your app...").start()
    try:
        profile = cmd_learn(
            creds["LLM_API_KEY"],
            creds["LLM_BASE_URL"],
            creds["LLM_MODEL"],
        )
        sp.stop("Product profile generated")
    except Exception:
        sp.fail("Failed to generate profile")
        raise

    db = __import__("db")
    env_writer = __import__("env_writer")

    db_path = db.get_default_db_path()
    env_path = db.get_env_path()
    profiles_path = (
        Path(__file__).resolve().parent / "profiles" / "r_saas_community.json"
    )

    sp = Spinner("Saving configuration...").start()
    db.init_db(db_path)
    env_writer.write_env(env_path, creds)
    db.save_product(db_path, profile)
    db.seed_default_community(db_path, str(profiles_path))
    sp.stop("Configuration saved")

    _update_gitignore()

    print(f"\n  Setup complete {_GREEN}✓{_RESET}\n")
    print(f"  Run {_BOLD}npx post-pilot serve{_RESET} to launch the web UI.\n")


def cmd_serve(port: int) -> None:
    db = __import__("db")
    db_path = Path(db.get_default_db_path())

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
    db_path = db.get_default_db_path()
    env_path = db.get_env_path()

    if args.command == "configure":
        creds = cmd_configure()
        env_writer.write_env(env_path, creds)
        print(f"\n  {_GREEN}✓{_RESET} Saved credentials to {env_path}")
        return

    if args.command == "learn":
        creds = env_writer.read_env(env_path)
        required = ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"]
        missing = [key for key in required if not creds.get(key)]
        if missing:
            print("Missing LLM credentials. Run `npx post-pilot configure` first.")
            sys.exit(1)

        db.init_db(db_path)

        sp = Spinner("Learning about your app...").start()
        try:
            profile = cmd_learn(
                creds["LLM_API_KEY"],
                creds["LLM_BASE_URL"],
                creds["LLM_MODEL"],
            )
            sp.stop("Product profile generated")
        except Exception:
            sp.fail("Failed to generate profile")
            raise

        _print_profile(profile)
        profile["onboarded"] = 0
        db.save_product(db_path, profile)
        print(f"  {_GREEN}✓{_RESET} Product profile saved.\n")
        return

    if args.command == "serve":
        cmd_serve(args.port)
        return

    raise RuntimeError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
