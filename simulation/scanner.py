import json
import importlib
from pathlib import Path
from typing import Protocol, cast


class _ResponseMessage(Protocol):
    content: str | None


class _ResponseChoice(Protocol):
    message: _ResponseMessage


class _ChatCompletionResponse(Protocol):
    choices: list[_ResponseChoice]


class _CompletionsAPI(Protocol):
    def create(
        self, *, model: str, messages: list[dict[str, str]], temperature: float
    ) -> _ChatCompletionResponse: ...


class _ChatAPI(Protocol):
    completions: _CompletionsAPI


class _OpenAIClient(Protocol):
    chat: _ChatAPI


class _OpenAIClientFactory(Protocol):
    def __call__(self, *, api_key: str, base_url: str) -> _OpenAIClient: ...


SKIP_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    ".next",
    "__pycache__",
    ".venv",
    "venv",
    "vendor",
    ".post-pilot",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "coverage",
    ".nyc_output",
}

SCAN_NAMES = {
    "README.md",
    "README.rst",
    "README.txt",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "composer.json",
    "Gemfile",
}

MAX_FILE_SIZE = 50_000
MAX_INDIVIDUAL = 4_000
MAX_TOTAL = 16_000

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
            sub = _build_tree(item, depth + 1, max_depth)
            if sub:
                lines.append(sub)
        else:
            lines.append(f"{prefix}{item.name}")

    return "\n".join(lines)


def build_llm_context(root: Path) -> str:
    files = discover_files(root)
    parts: list[str] = []
    total = 0

    tree = _build_tree(root)
    tree_section = f"## File Structure\n```\n{tree}\n```\n"
    parts.append(tree_section)
    total += len(tree_section)

    for file_path in files:
        if total >= MAX_TOTAL:
            break
        content = _read_truncated(file_path)
        rel = file_path.relative_to(root)
        section = f"## {rel}\n```\n{content}\n```\n"
        if total + len(section) > MAX_TOTAL:
            remaining = MAX_TOTAL - total
            section = section[:remaining]
        parts.append(section)
        total += len(section)

    return "\n".join(parts)


def generate_profile(
    root: Path, api_key: str, base_url: str, model: str
) -> dict[str, str]:
    context = build_llm_context(root)
    openai_module = importlib.import_module("openai")
    openai_client = cast(_OpenAIClientFactory, getattr(openai_module, "OpenAI"))
    client = openai_client(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": PROFILE_PROMPT + context}],
        temperature=0.3,
    )
    text = response.choices[0].message.content or "{}"
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return cast(dict[str, str], json.loads(text.strip()))
