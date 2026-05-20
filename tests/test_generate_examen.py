"""Tests for scripts.generate_examen.generate (CLI scaffold generator)."""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).parent.parent
FIXTURE = ROOT / "scripts" / "fixtures" / "examen_scaffold_sample.json"


def _today() -> dict:
    return {
        "date": "2026-05-19",
        "liturgical": {
            "title": "Tuesday of the 7th Week of Easter",
            "season": "Easter",
            "rank": "Weekday",
            "color": "white",
        },
        "readings": [
            {"kind": "gospel", "citation": "John 17:1-11",
             "text": "Father, the hour has come..."},
        ],
        "walkWithHim": {"oneTruthToCarry": "The hour is His and mine."},
    }


def _fixture_content() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_generate_returns_valid_scaffold():
    from scripts import generate_examen
    fake = {"content": _fixture_content(), "usage": {}}
    with patch("scripts.generate_examen.call_claude_cli", return_value=fake):
        result = generate_examen.generate(_today(), yesterday=None)
    scaffold = result["scaffold"]
    assert len(scaffold["stations"]) == 5
    assert scaffold["stations"][0]["kind"] == "gratitude"
    assert result["model"] == "claude-code-cli/subscription"
    assert "generatedAt" in result
    assert result["continuityUsed"] is False


def test_generate_strips_markdown_fences():
    from scripts import generate_examen
    wrapped = "```json\n" + _fixture_content() + "\n```"
    fake = {"content": wrapped, "usage": {}}
    with patch("scripts.generate_examen.call_claude_cli", return_value=fake):
        result = generate_examen.generate(_today(), yesterday=None)
    scaffold = result["scaffold"]
    assert len(scaffold["stations"]) == 5
    assert scaffold["stations"][0]["kind"] == "gratitude"


def test_generate_raises_on_malformed_json():
    from scripts import generate_examen
    fake = {"content": "not json at all", "usage": {}}
    with patch("scripts.generate_examen.call_claude_cli", return_value=fake):
        with pytest.raises(json.JSONDecodeError):
            generate_examen.generate(_today(), yesterday=None)
