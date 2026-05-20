"""Tests for validate_examen + schemaVersion 3 acceptance in validate_output."""
from __future__ import annotations
import copy
import json
from pathlib import Path

import pytest

from scripts.validate_examen import validate_examen, ExamenValidationError
from scripts.validate_output import validate, ValidationError

ROOT = Path(__file__).parent.parent
FIXTURE = ROOT / "scripts" / "fixtures" / "examen_scaffold_sample.json"
CCC_PATH = ROOT / "corpus" / "embeddings" / "ccc.parquet"


def _scaffold() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_valid_scaffold_passes():
    validate_examen(_scaffold())


def test_missing_station_fails():
    bad = _scaffold()
    bad["stations"] = bad["stations"][:4]
    with pytest.raises(ExamenValidationError, match="exactly 5"):
        validate_examen(bad)


def test_wrong_order_fails():
    bad = _scaffold()
    bad["stations"][0], bad["stations"][1] = bad["stations"][1], bad["stations"][0]
    with pytest.raises(ExamenValidationError, match="order"):
        validate_examen(bad)


def test_empty_prompt_fails():
    bad = _scaffold()
    bad["stations"][0]["prompt"] = ""
    with pytest.raises(ExamenValidationError, match="prompt"):
        validate_examen(bad)


def test_validate_output_accepts_schema_v3_with_examen():
    if not CCC_PATH.exists():
        return  # graceful skip when CCC corpus not present on this machine
    payload = {
        "schemaVersion": 3,
        "date": "2026-05-19",
        "liturgical": {"season": "Easter", "week": "7th",
                        "color": "white", "rank": "Weekday",
                        "title": "Tuesday of the 7th Week of Easter",
                        "lectionaryCycle": None, "weekdayCycle": "I"},
        "saint": None,
        "readings": [{
            "kind": "gospel", "citation": "Jn 17:1-11", "title": "Gospel",
            "text": "Father, the hour has come...",
            "translation": "NABRE",
            "exegesis": {
                "summary": "Jesus prays the priestly prayer.",
                "patristicQuotes": [{"father": "Augustine", "work": "Tract",
                                       "quote": "..."}],
                "cccReferences": [{"paragraph": 260, "title": "Trinity"}],
                "thematicConnection": "Priestly prayer fulfilled.",
            },
        }],
        "synthesis": {"title": "...", "body": "Body text suffices."},
        "generation": {"model": "claude-code-cli/subscription",
                        "promptTokens": 0, "completionTokens": 0,
                        "generatedAt": "2026-05-19T00:00:00Z",
                        "corpusVersion": "v1.0"},
        "examen": _scaffold(),
    }
    validate(payload, ccc_path=CCC_PATH)  # must not raise
