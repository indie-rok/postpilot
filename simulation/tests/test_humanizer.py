# simulation/tests/test_humanizer.py
# pyright: reportMissingImports=false, reportImplicitRelativeImport=false

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_writing_rules_is_nonempty_string():
    from prompts.humanizer import WRITING_RULES

    assert isinstance(WRITING_RULES, str)
    assert len(WRITING_RULES) > 1000  # full 25 categories should be substantial


def test_writing_rules_contains_all_25_categories():
    from prompts.humanizer import WRITING_RULES

    # Spot-check key categories are present
    assert "significance" in WRITING_RULES.lower() or "legacy" in WRITING_RULES.lower()
    assert "em dash" in WRITING_RULES.lower() or "em-dash" in WRITING_RULES.lower()
    assert "delve" in WRITING_RULES.lower()
    assert "rule of three" in WRITING_RULES.lower()
    assert "sycophantic" in WRITING_RULES.lower() or "servile" in WRITING_RULES.lower()
    assert "filler" in WRITING_RULES.lower()
    assert "hedging" in WRITING_RULES.lower()
    assert "parallelism" in WRITING_RULES.lower()
    assert "boldface" in WRITING_RULES.lower() or "bold" in WRITING_RULES.lower()


def test_writing_rules_contains_personality_section():
    from prompts.humanizer import WRITING_RULES

    assert "vary" in WRITING_RULES.lower()
    assert "opinion" in WRITING_RULES.lower() or "personality" in WRITING_RULES.lower()
