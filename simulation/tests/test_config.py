"""Tests for simulation configuration."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.simulation_config import (
    PLATFORM_CONFIG,
    ACTIVITY_CONFIGS,
    TIME_CONFIG,
    ARCHETYPE_NAMES,
)


def test_platform_config_is_reddit():
    assert PLATFORM_CONFIG["recsys_type"] == "reddit"


def test_platform_config_no_self_rating():
    assert PLATFORM_CONFIG["allow_self_rating"] is False


def test_platform_config_shows_score():
    assert PLATFORM_CONFIG["show_score"] is True


def test_time_config_has_required_keys():
    required = {
        "total_hours",
        "agents_per_hour_min",
        "agents_per_hour_max",
        "peak_hours",
        "peak_multiplier",
        "off_peak_hours",
        "off_peak_multiplier",
    }
    for key in required:
        assert key in TIME_CONFIG, f"Missing time config key: {key}"


def test_total_hours_positive():
    assert TIME_CONFIG["total_hours"] > 0


def test_activity_configs_cover_all_archetypes():
    for name in ARCHETYPE_NAMES:
        assert name in ACTIVITY_CONFIGS, f"Missing activity config for '{name}'"


def test_activity_config_structure():
    required_keys = {"activity_level", "active_hours", "vote_probability"}
    for name, config in ACTIVITY_CONFIGS.items():
        for key in required_keys:
            assert key in config, f"'{name}' missing key '{key}'"


def test_activity_level_range():
    for name, config in ACTIVITY_CONFIGS.items():
        assert 0.0 <= config["activity_level"] <= 1.0, (
            f"'{name}' activity_level out of range: {config['activity_level']}"
        )


def test_active_hours_valid():
    for name, config in ACTIVITY_CONFIGS.items():
        for h in config["active_hours"]:
            assert 0 <= h <= 23, f"'{name}' has invalid active_hour: {h}"
