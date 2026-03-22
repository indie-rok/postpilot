"""Tests for parse_post.py — markdown to plain text extraction."""

import os
import tempfile
import pytest

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from parse_post import parse_markdown_post


SAMPLE_MARKDOWN = """# r/SaaS

---

**We built a tool that predicts employee burnout. Here's what we learned.**

---

Hey r/SaaS — Maya here, co-founder of FlowPulse.

Quick background: I spent 4 years running People Ops.

## The problem

Remote teams are burning out in silence.

## What we built

**FlowPulse** is a lightweight pulse check platform.

- **Starter** — $4/user/mo
- **Growth** — $8/user/mo

[flowpulse.io](https://flowpulse.io)
"""


def test_parse_extracts_title():
    result = parse_markdown_post(SAMPLE_MARKDOWN)
    assert (
        result["title"]
        == "We built a tool that predicts employee burnout. Here's what we learned."
    )


def test_parse_extracts_body():
    result = parse_markdown_post(SAMPLE_MARKDOWN)
    body = result["body"]
    assert "Maya here, co-founder of FlowPulse" in body
    assert "Remote teams are burning out" in body
    assert "**" not in body
    assert "##" not in body


def test_parse_preserves_list_items():
    result = parse_markdown_post(SAMPLE_MARKDOWN)
    body = result["body"]
    assert "$4/user/mo" in body
    assert "$8/user/mo" in body


def test_parse_strips_links_keeps_text():
    result = parse_markdown_post(SAMPLE_MARKDOWN)
    body = result["body"]
    assert "flowpulse.io" in body
    assert "[" not in body
    assert "](" not in body


def test_parse_from_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(SAMPLE_MARKDOWN)
        f.flush()
        result = parse_markdown_post(open(f.name).read())
    os.unlink(f.name)
    assert result["title"] != ""
    assert result["body"] != ""
