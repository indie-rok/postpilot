"""Tests for agent profile data integrity."""

import json
import os
import pytest

PROFILES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "profiles", "r_saas_community.json"
)

REQUIRED_FIELDS = [
    "username",
    "realname",
    "bio",
    "persona",
    "age",
    "gender",
    "mbti",
    "country",
    "profession",
    "interested_topics",
]

VALID_MBTI = [
    "INTJ",
    "INTP",
    "ENTJ",
    "ENTP",
    "INFJ",
    "INFP",
    "ENFJ",
    "ENFP",
    "ISTJ",
    "ISFJ",
    "ESTJ",
    "ESFJ",
    "ISTP",
    "ISFP",
    "ESTP",
    "ESFP",
]


@pytest.fixture
def profiles():
    with open(PROFILES_PATH) as f:
        return json.load(f)


def test_has_18_agents(profiles):
    assert len(profiles) == 18


def test_all_required_fields_present(profiles):
    for i, profile in enumerate(profiles):
        for field in REQUIRED_FIELDS:
            assert field in profile, (
                f"Agent {i} ({profile.get('username', '?')}) missing '{field}'"
            )


def test_usernames_are_unique(profiles):
    usernames = [p["username"] for p in profiles]
    assert len(usernames) == len(set(usernames))


def test_valid_mbti_types(profiles):
    for profile in profiles:
        assert profile["mbti"] in VALID_MBTI, (
            f"{profile['username']} has invalid MBTI: {profile['mbti']}"
        )


def test_persona_is_detailed(profiles):
    for profile in profiles:
        assert len(profile["persona"]) >= 200, (
            f"{profile['username']} persona too short: {len(profile['persona'])} chars"
        )


def test_gender_values(profiles):
    for profile in profiles:
        assert profile["gender"] in ("male", "female", "other"), (
            f"{profile['username']} has invalid gender: {profile['gender']}"
        )


def test_age_range(profiles):
    for profile in profiles:
        assert 18 <= profile["age"] <= 70, (
            f"{profile['username']} has unrealistic age: {profile['age']}"
        )


def test_interested_topics_non_empty(profiles):
    for profile in profiles:
        assert len(profile["interested_topics"]) >= 1, (
            f"{profile['username']} has no interested_topics"
        )
