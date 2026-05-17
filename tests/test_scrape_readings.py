"""Tests for Universalis daily Mass readings scraper."""
from pathlib import Path

import pytest

from scripts.scrape_readings import (
    ScrapeError,
    date_to_path,
    fetch_day,
    parse_readings,
)

FIX = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_date_to_path_format():
    # 2026-05-17 -> 20260517 (Universalis YYYYMMDD)
    assert date_to_path("2026-05-17") == "20260517"
    assert date_to_path("2024-01-01") == "20240101"
    assert date_to_path("2024-12-31") == "20241231"


def test_date_to_path_rejects_bad_input():
    with pytest.raises(ScrapeError):
        date_to_path("2026/05/17")
    with pytest.raises(ScrapeError):
        date_to_path("not-a-date")


def test_sunday_has_four_readings():
    out = parse_readings(_read("universalis_sunday.html"))
    kinds = [r["kind"] for r in out["readings"]]
    assert "first_reading" in kinds
    assert "psalm" in kinds
    assert "second_reading" in kinds
    assert "gospel" in kinds


def test_weekday_has_three_readings():
    out = parse_readings(_read("universalis_weekday.html"))
    kinds = [r["kind"] for r in out["readings"]]
    assert "first_reading" in kinds
    assert "psalm" in kinds
    assert "gospel" in kinds
    assert "second_reading" not in kinds


def test_psalm_has_refrain():
    out = parse_readings(_read("universalis_sunday.html"))
    psalm = next(r for r in out["readings"] if r["kind"] == "psalm")
    assert psalm.get("refrain"), f"refrain missing: {psalm}"
    assert len(psalm["refrain"]) > 5


def test_readings_have_citation_and_text():
    out = parse_readings(_read("universalis_sunday.html"))
    for r in out["readings"]:
        assert r.get("citation"), f"missing citation in {r}"
        assert r.get("text") and len(r["text"]) > 50, f"missing text in {r['kind']}"


def test_translation_field_set():
    out = parse_readings(_read("universalis_sunday.html"))
    # Universalis US edition uses NABRE-compatible text under a publishing
    # arrangement; we report 'Universalis (US)' as the translation marker
    # since the exact arrangement varies by year.
    for r in out["readings"]:
        assert r.get("translation")


def test_empty_html_raises():
    with pytest.raises(ScrapeError):
        parse_readings("<html><body>nothing here</body></html>")


def test_network_error_raises(monkeypatch):
    """fetch_day must raise ScrapeError when the HTTP layer fails."""
    import requests

    def _boom(*a, **kw):
        raise requests.ConnectionError("network unreachable")

    monkeypatch.setattr(requests, "get", _boom)
    with pytest.raises(ScrapeError):
        fetch_day("2026-05-17")
