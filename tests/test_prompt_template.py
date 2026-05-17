from scripts.prompt_template import SYSTEM_PROMPT, build_user_prompt

def test_system_prompt_mentions_magisterium():
    assert "Magisterium" in SYSTEM_PROMPT

def test_system_prompt_forbids_hallucinated_ccc():
    assert "CCC" in SYSTEM_PROMPT
    assert "invent" in SYSTEM_PROMPT.lower() or "hallucinate" in SYSTEM_PROMPT.lower() or "do not" in SYSTEM_PROMPT.lower()

def test_user_prompt_includes_readings_and_retrieved_context():
    out = build_user_prompt(
        readings=[{"kind": "gospel", "title": "Gospel",
                    "citation": "Jn 14:23-29", "text": "Jesus said..."}],
        liturgical={"title": "6th Sunday of Easter", "season": "Easter",
                    "week": "6th Week of Easter", "rank": "Sunday",
                    "color": "white", "lectionaryCycle": "C",
                    "date": "2026-05-17"},
        saint={"name": "St. Paschal Baylon", "rank": "Optional Memorial",
                "bio": "16th-cent. Franciscan"},
        retrieved_per_reading=[{
            "catena": [{"father": "Augustine", "work": "Tract 76",
                          "quote": "Father and Son make their dwelling..."}],
            "ccc": [{"paragraph": 260, "title": "Trinity", "text": "..."}],
        }],
    )
    assert "Jesus said..." in out
    assert "Augustine" in out
    assert "Father and Son make their dwelling" in out
    assert "CCC 260" in out
    assert "St. Paschal Baylon" in out
    assert "JSON" in out

def test_user_prompt_handles_no_saint():
    out = build_user_prompt(
        readings=[{"kind": "gospel", "title": "Gospel",
                    "citation": "Mt 5:1", "text": "..."}],
        liturgical={"title": "Tuesday", "season": "Easter", "week": "6th",
                    "rank": "Weekday", "color": "white",
                    "weekdayCycle": "II", "date": "2026-05-19"},
        saint=None,
        retrieved_per_reading=[{"catena": [], "ccc": []}],
    )
    assert "Saint of the day" not in out

def test_user_prompt_ordering_matches_input():
    out = build_user_prompt(
        readings=[
            {"kind": "first_reading", "title": "First Reading",
              "citation": "Acts 15:1", "text": "First..."},
            {"kind": "gospel", "title": "Gospel",
              "citation": "Jn 14:1", "text": "Gospel..."},
        ],
        liturgical={"title": "x", "season": "y", "week": "z",
                     "rank": "Sunday", "color": "white"},
        saint=None,
        retrieved_per_reading=[{"catena": [], "ccc": []},
                                {"catena": [], "ccc": []}],
    )
    # First Reading section must appear before Gospel section
    assert out.index("First Reading") < out.index("Gospel —")
