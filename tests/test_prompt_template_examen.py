"""Tests for build_examen_prompt."""
from scripts.prompt_template import build_examen_prompt


def _sample_today() -> dict:
    return {
        "date": "2026-05-19",
        "liturgical": {
            "title": "Tuesday of the 7th Week of Easter",
            "season": "Easter",
            "rank": "Weekday",
            "color": "white",
        },
        "readings": [
            {"kind": "first_reading", "citation": "Acts 20:17-27",
             "text": "Paul exhorts the elders."},
            {"kind": "gospel", "citation": "John 17:1-11",
             "text": "Father, the hour has come..."},
        ],
        "walkWithHim": {
            "oneTruthToCarry": "The hour is His and mine.",
        },
    }


def test_examen_prompt_includes_all_5_stations():
    today = _sample_today()
    prompt = build_examen_prompt(today, yesterday=None)
    low = prompt.lower()
    for kind in ("gratitude", "petition", "review", "sorrow", "renewal"):
        assert kind in low, f"missing station kind: {kind}"
    assert "with-him" in low
    assert "bible-entry-icb" in low
    # The prompt asks the model to OUTPUT a scaffold; schemaVersion is set
    # by the orchestrator, not by the model.
    assert "schemaversion" not in low


def test_examen_prompt_with_yesterday_continuity():
    today = _sample_today()
    yesterday = {"resolution": "to forgive my brother", "mood": "desolation"}
    prompt = build_examen_prompt(today, yesterday=yesterday)
    assert "forgive my brother" in prompt.lower()


def test_examen_prompt_without_yesterday_omits_continuity():
    today = _sample_today()
    prompt = build_examen_prompt(today, yesterday=None)
    assert "yesterday you resolved" not in prompt.lower()
