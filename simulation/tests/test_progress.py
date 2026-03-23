"""Tests for emit_progress() output format."""

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
