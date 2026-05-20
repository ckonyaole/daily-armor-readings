"""End-to-end test: generate.main() with --use-claude-cli wires Examen in."""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
FIX = Path(__file__).parent / "fixtures"
EXAMEN_FIXTURE = ROOT / "scripts" / "fixtures" / "examen_scaffold_sample.json"


def _examen_content() -> str:
    return EXAMEN_FIXTURE.read_text(encoding="utf-8")


def _morning_ai_json_for(readings: list[dict]) -> str:
    """Build a minimal morning-call AI JSON matching the reading kinds."""
    out = {
        "schemaVersion": 2,
        "readings": [
            {
                "kind": r["kind"],
                "exegesis": {
                    "summary": "Stub summary.",
                    "patristicQuotes": [{"father": "Augustine",
                                          "work": "Tract", "quote": "..."}],
                    "cccReferences": [{"paragraph": 260, "title": "Trinity"}],
                    "thematicConnection": "Stub link.",
                },
            }
            for r in readings
        ],
        "synthesis": {"title": "Stub", "body": "Stub synthesis body text."},
    }
    return json.dumps(out)


def test_generate_includes_examen_when_use_claude_cli(tmp_path):
    # Fall back gracefully if fixtures are absent on this machine.
    fixture_path = FIX / "universalis_weekday.html"
    if not fixture_path.exists():
        return

    # We can't know the readings shape until the fixture parses, so parse first.
    from scripts.scrape_readings import parse_readings
    html = fixture_path.read_text(encoding="utf-8")
    readings = parse_readings(html)["readings"]
    morning_content = _morning_ai_json_for(readings)

    calls = {"n": 0}

    def fake_morning(*, system, user, **kw):
        calls["n"] += 1
        return {"content": morning_content, "usage": {}}

    def fake_examen(*, system, user, **kw):
        return {"content": _examen_content(), "usage": {}}

    out = tmp_path / "out.json"
    from scripts import generate as g
    with patch("scripts.generate.call_claude_cli", side_effect=fake_morning), \
         patch("scripts.generate_examen.call_claude_cli", side_effect=fake_examen):
        rc = g.main([
            "--date", "2026-05-19", "--out", str(out),
            "--fixture", str(fixture_path), "--use-claude-cli",
        ])

    assert rc == 0, f"main returned {rc}"
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == 3
    assert "examen" in payload
    assert len(payload["examen"]["stations"]) == 5
