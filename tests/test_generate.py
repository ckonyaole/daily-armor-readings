from pathlib import Path
import json
from unittest.mock import patch, MagicMock
import pytest

ROOT = Path(__file__).parent.parent
FIX = Path(__file__).parent / "fixtures"

def test_dry_run_writes_valid_stub(tmp_path):
    from scripts import generate as g
    out = tmp_path / "2026-05-17.json"
    fixture = str(FIX / "universalis_sunday.html")
    rc = g.main(["--date", "2026-05-17", "--out", str(out),
                  "--dry-run", "--fixture", fixture])
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == 1
    assert payload["date"] == "2026-05-17"
    assert len(payload["readings"]) >= 3

def test_scrape_failure_writes_placeholder(tmp_path):
    from scripts import generate as g
    out = tmp_path / "2026-05-17.json"
    rc = g.main(["--date", "2026-05-17", "--out", str(out),
                  "--dry-run", "--fixture", "/nonexistent.html"])
    assert rc == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "scrape_failed" in payload["status"]
