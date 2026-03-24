import os
import sys
import importlib
from pathlib import Path
from typing import Callable, cast

_ = sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

scanner = importlib.import_module("scanner")
DiscoverFiles = Callable[[Path], list[Path]]
BuildContext = Callable[[Path], str]
discover_files = cast(DiscoverFiles, getattr(scanner, "discover_files"))
build_llm_context = cast(BuildContext, getattr(scanner, "build_llm_context"))


def test_discover_finds_readme(tmp_path: Path):
    _ = (tmp_path / "README.md").write_text("# My App\nA cool thing")
    files = discover_files(tmp_path)
    assert any(f.name == "README.md" for f in files)


def test_discover_skips_node_modules(tmp_path: Path):
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    _ = (nm / "index.js").write_text("module.exports = {}")
    _ = (tmp_path / "README.md").write_text("# App")
    files = discover_files(tmp_path)
    paths = [str(f) for f in files]
    assert not any("node_modules" in p for p in paths)


def test_discover_skips_large_files(tmp_path: Path):
    _ = (tmp_path / "big.txt").write_text("x" * 60_000)
    _ = (tmp_path / "small.txt").write_text("hello")
    _ = (tmp_path / "README.md").write_text("# App")
    files = discover_files(tmp_path)
    names = [f.name for f in files]
    assert "README.md" in names
    assert "big.txt" not in names


def test_discover_reads_docs(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    _ = (docs / "guide.md").write_text("# Guide\nSome content")
    _ = (tmp_path / "README.md").write_text("# App")
    files = discover_files(tmp_path)
    names = [f.name for f in files]
    assert "guide.md" in names


def test_build_llm_context_truncates(tmp_path: Path):
    _ = (tmp_path / "README.md").write_text("A" * 10_000)
    context = build_llm_context(tmp_path)
    assert len(context) <= 17_000
    assert "README.md" in context


def test_build_llm_context_includes_tree(tmp_path: Path):
    _ = (tmp_path / "README.md").write_text("# App")
    src = tmp_path / "src"
    src.mkdir()
    _ = (src / "main.py").write_text("print('hi')")
    context = build_llm_context(tmp_path)
    assert "File Structure" in context
    assert "src/" in context
