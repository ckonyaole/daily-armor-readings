"""Tests for USCCB daily readings scraper."""
from pathlib import Path

import pytest

from scripts.scrape_usccb import (
    ScrapeError,
    date_to_path,
    fetch_day,
    parse_readings,
)

FIX = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_date_to_path_format():
    # ISO 2026-05-17 -> USCCB MMDDYY 051726
    assert date_to_path("2026-05-17") == "051726"
    assert date_to_path("2024-01-01") == "010124"
    assert date_to_path("2024-12-31") == "123124"


def test_date_to_path_rejects_bad_input():
    with pytest.raises(ScrapeError):
        date_to_path("2026/05/17")
    with pytest.raises(ScrapeError):
        date_to_path("not-a-date")


def test_sunday_has_four_readings():
    out = parse_readings(_read("usccb_sunday.html"))
    kinds = [r["kind"] for r in out["readings"]]
    assert "first_reading" in kinds
    assert "psalm" in kinds
    assert "second_reading" in kinds
    assert "gospel" in kinds


def test_weekday_has_three_readings():
    out = parse_readings(_read("usccb_weekday.html"))
    kinds = [r["kind"] for r in out["readings"]]
    assert "first_reading" in kinds
    assert "psalm" in kinds
    assert "gospel" in kinds
    assert "second_reading" not in kinds


def test_psalm_has_refrain():
    out = parse_readings(_read("usccb_sunday.html"))
    psalm = next(r for r in out["readings"] if r["kind"] == "psalm")
    assert psalm.get("refrain"), f"refrain missing: {psalm}"
    assert len(psalm["refrain"]) > 5


def test_readings_have_citation_and_text():
    out = parse_readings(_read("usccb_sunday.html"))
    for r in out["readings"]:
        assert r.get("citation"), f"missing citation: {r}"
        assert r.get("text") and len(r["text"]) > 50, f"missing text: {r}"


def test_translation_is_nabre():
    out = parse_readings(_read("usccb_sunday.html"))
    for r in out["readings"]:
        assert r.get("translation") == "NABRE"


def test_empty_html_raises():
    with pytest.raises(ScrapeError):
        parse_readings("<html><body></body></html>")


def test_network_error_raises(monkeypatch):
    """fetch_day must raise ScrapeError on HTTP failure (not requests exceptions)."""
    import requests

    class _Boom:
        def raise_for_status(self):
            raise requests.HTTPError("404 Not Found")

        text = ""

    def _fake_get(*a, **kw):
        return _Boom()

    monkeypatch.setattr(requests, "get", _fake_get)
    with pytest.raises(ScrapeError):
        fetch_day("999999")
