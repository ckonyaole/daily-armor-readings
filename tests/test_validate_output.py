from pathlib import Path
import pandas as pd
import pytest
from scripts.validate_output import validate, ValidationError

def _fake_ccc(tmp_path):
    """Tiny CCC corpus with paragraphs 1-2865 (just enough for membership check)."""
    rows = [{"paragraph": p, "text": "..."} for p in range(1, 2866)]
    df = pd.DataFrame(rows)
    out = tmp_path / "ccc.parquet"
    df.to_parquet(out)
    return out

VALID_PAYLOAD = {
    "schemaVersion": 1,
    "date": "2026-05-17",
    "liturgical": {"season": "Easter", "week": "6th", "color": "white",
                    "rank": "Sunday", "title": "6th Sunday of Easter",
                    "lectionaryCycle": "C", "weekdayCycle": None},
    "saint": None,
    "readings": [{
        "kind": "gospel", "citation": "Jn 14:23-29", "title": "Gospel",
        "text": "...", "translation": "NABRE",
        "exegesis": {
            "summary": "Jesus promises the indwelling Trinity.",
            "patristicQuotes": [{"father": "Augustine", "work": "Tract 76", "quote": "..."}],
            "cccReferences": [{"paragraph": 260, "title": "Trinity dwells"}],
            "thematicConnection": "Echoes the First Reading."
        }
    }],
    "synthesis": {"title": "...", "body": "Some real body content here for testing."},
    "generation": {"model": "anthropic/claude-opus-4-7", "promptTokens": 1,
                    "completionTokens": 1, "generatedAt": "2026-05-17T00:00:00Z",
                    "corpusVersion": "v1"}
}

def test_valid_payload_passes(tmp_path):
    ccc = _fake_ccc(tmp_path)
    validate(VALID_PAYLOAD, ccc_path=ccc)

def test_hallucinated_ccc_paragraph_fails(tmp_path):
    ccc = _fake_ccc(tmp_path)
    bad = {**VALID_PAYLOAD}
    bad["readings"] = [{**VALID_PAYLOAD["readings"][0],
                         "exegesis": {**VALID_PAYLOAD["readings"][0]["exegesis"],
                                       "cccReferences": [{"paragraph": 9999, "title": "fake"}]}}]
    with pytest.raises(ValidationError, match="CCC.*9999"):
        validate(bad, ccc_path=ccc)

def test_wrong_schema_version_fails(tmp_path):
    ccc = _fake_ccc(tmp_path)
    bad = {**VALID_PAYLOAD, "schemaVersion": 99}
    with pytest.raises(ValidationError, match="schemaVersion"):
        validate(bad, ccc_path=ccc)

def test_missing_synthesis_fails(tmp_path):
    ccc = _fake_ccc(tmp_path)
    bad = {k: v for k, v in VALID_PAYLOAD.items() if k != "synthesis"}
    with pytest.raises(ValidationError, match="synthesis"):
        validate(bad, ccc_path=ccc)

def test_empty_synthesis_body_fails(tmp_path):
    ccc = _fake_ccc(tmp_path)
    bad = {**VALID_PAYLOAD, "synthesis": {"title": "...", "body": ""}}
    with pytest.raises(ValidationError, match=r"synthesis\.body"):
        validate(bad, ccc_path=ccc)

def test_empty_readings_fails(tmp_path):
    ccc = _fake_ccc(tmp_path)
    bad = {**VALID_PAYLOAD, "readings": []}
    with pytest.raises(ValidationError, match="readings"):
        validate(bad, ccc_path=ccc)

def test_invalid_reading_kind_fails(tmp_path):
    ccc = _fake_ccc(tmp_path)
    bad = {**VALID_PAYLOAD}
    bad["readings"] = [{**VALID_PAYLOAD["readings"][0], "kind": "weird_kind"}]
    with pytest.raises(ValidationError, match="kind"):
        validate(bad, ccc_path=ccc)

def test_missing_attribution_warns_not_fails(tmp_path, capsys):
    ccc = _fake_ccc(tmp_path)
    bad = {**VALID_PAYLOAD}
    bad["readings"] = [{**VALID_PAYLOAD["readings"][0],
                         "exegesis": {**VALID_PAYLOAD["readings"][0]["exegesis"],
                                       "patristicQuotes": [{"father": "", "work": "", "quote": "..."}]}}]
    validate(bad, ccc_path=ccc)  # should not raise
    captured = capsys.readouterr()
    assert "warning" in captured.out.lower() or "warning" in captured.err.lower()
