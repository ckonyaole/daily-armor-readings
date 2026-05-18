"""Daily orchestrator: scrape -> retrieve -> prompt -> call -> validate -> write."""
from __future__ import annotations
import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

from scripts.scrape_readings import fetch_day, parse_readings, ScrapeError
from scripts.scrape_catholic_org import (
    fetch_day as fetch_day_co,
    parse_readings as parse_readings_co,
)
from scripts.retrieve import Retriever
from scripts.prompt_template import SYSTEM_PROMPT, build_user_prompt
from scripts.call_openrouter import call_chat, OpenRouterError
from scripts.call_claude_cli import call_cli as call_claude_cli, ClaudeCliError
from scripts.validate_output import validate, ValidationError
from scripts.liturgical import season_for, lectionary_cycle, weekday_cycle
from scripts.fetch_bible_passage import fetch as fetch_passage, PassageFetchError

ROOT = Path(__file__).parent.parent
MODEL = "anthropic/claude-opus-4-7"
CORPUS_VERSION = "v1.0"

import json as _json

OVERRIDES_PATH = ROOT / "scripts" / "us_feast_overrides.json"

def _load_overrides() -> dict:
    if not OVERRIDES_PATH.exists():
        return {}
    data = _json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}

def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--out", default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="skip OpenRouter call; write debug stub")
    parser.add_argument("--fixture", default=None,
                        help="Path to fixture HTML to use instead of live fetch")
    parser.add_argument("--use-claude-cli", action="store_true",
                        help="Use local `claude` CLI (subscription auth) instead "
                             "of OpenRouter API. Requires `claude` on PATH + interactive sign-in.")
    args = parser.parse_args(argv)

    d = date.fromisoformat(args.date)
    out_path = Path(args.out) if args.out else ROOT / "output" / f"{args.date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    overrides = _load_overrides()
    override = overrides.get(args.date)

    # 1. Get readings — either from override (citation-based passage fetch)
    #    or from Universalis scrape.
    if override and "readings" in override:
        print(f"US feast override: {args.date} -> {override['title']} (fetching passages by citation)")
        readings = []
        for r in override["readings"]:
            citation = r["citation"]
            try:
                text = fetch_passage(citation)
            except PassageFetchError as e:
                _write_placeholder(out_path, args.date, f"passage_fetch_failed: {citation}: {e}")
                print(f"PASSAGE FETCH FAILED for {citation}: {e}", file=sys.stderr)
                return 1
            readings.append({
                "kind": r["kind"],
                "title": r.get("title", r["kind"].replace("_", " ").title()),
                "citation": citation,
                "text": text,
                "translation": "RSVCE",
            })
    else:
        readings = []
        scrape_errors: list[str] = []
        # Sources tried in order: fixture > Universalis (UK) > catholic.org (US)
        # Catholic.org is reachable from US campus networks where Universalis
        # is blocked by Geo-IP filters (e.g. Dillard.edu).
        try:
            if args.fixture:
                html = Path(args.fixture).read_text(encoding="utf-8")
                readings = parse_readings(html)["readings"]
            else:
                html = fetch_day(args.date)
                readings = parse_readings(html)["readings"]
        except (ScrapeError, FileNotFoundError) as e:
            scrape_errors.append(f"universalis: {e}")
        if not readings and not args.fixture:
            print(f"Universalis scrape failed; trying catholic.org fallback...",
                  file=sys.stderr)
            try:
                html2 = fetch_day_co(args.date)
                readings = parse_readings_co(html2)["readings"]
                print(f"  ok: catholic.org returned {len(readings)} readings",
                      file=sys.stderr)
            except ScrapeError as e:
                scrape_errors.append(f"catholic.org: {e}")
        if not readings:
            joined = " | ".join(scrape_errors) or "unknown"
            _write_placeholder(out_path, args.date, f"scrape_failed: {joined}")
            print(f"ALL SCRAPE SOURCES FAILED: {joined}", file=sys.stderr)
            return 1

    # 2. Liturgical context
    season, color = season_for(d)
    is_sunday = d.weekday() == 6
    weekday_name = ["Monday", "Tuesday", "Wednesday", "Thursday",
                    "Friday", "Saturday", "Sunday"][d.weekday()]
    liturgical = {
        "season": season,
        "week": f"Week of {d.isoformat()}",
        "color": color,
        "rank": "Sunday" if is_sunday else "Weekday",
        "title": f"{weekday_name} - {d.strftime('%B %d, %Y')}",
        "lectionaryCycle": lectionary_cycle(d) if is_sunday else None,
        "weekdayCycle": None if is_sunday else weekday_cycle(d),
        "date": args.date,
    }

    if override:
        liturgical["title"] = override["title"]
        liturgical["rank"] = override["rank"]
        liturgical["color"] = override["color"]

    # 3. Retrieve per reading
    retriever = Retriever(
        catena_path=ROOT / "corpus" / "embeddings" / "catena.parquet",
        ccc_path=ROOT / "corpus" / "embeddings" / "ccc.parquet")
    retrieved_per: list[dict] = []
    for r in readings:
        gospel = None
        if r["kind"] == "gospel":
            cit = r.get("citation", "").lower()
            for g, prefixes in [
                ("matthew", ["matt", "mt "]),
                ("mark", ["mark", "mk "]),
                ("luke", ["luke", "lk "]),
                ("john", ["john", "jn "])]:
                if any(p in cit for p in prefixes):
                    gospel = g
                    break
        retrieved_per.append({
            "catena": retriever.retrieve_catena(r["text"][:1500], k=4, gospel=gospel),
            "ccc": retriever.retrieve_ccc(r["text"][:1500], k=6),
        })

    # 4. Prompt + call (or dry-run)
    user_prompt = build_user_prompt(
        readings=readings, liturgical=liturgical, saint=None,
        retrieved_per_reading=retrieved_per)

    if args.dry_run:
        ai_json = {
            "readings": [
                {"kind": r["kind"], "exegesis": {
                    "summary": "[dry-run]",
                    "patristicQuotes": [],
                    "cccReferences": [],
                    "thematicConnection": "[dry-run]",
                }} for r in readings
            ],
            "synthesis": {"title": "Dry run", "body": "[dry-run output]"},
        }
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        model_label = "dry-run"
    else:
        if args.use_claude_cli:
            try:
                res = call_claude_cli(system=SYSTEM_PROMPT, user=user_prompt)
                model_label = "claude-code-cli/subscription"
            except ClaudeCliError as e:
                print(f"CLAUDE CLI FAILED: {e}", file=sys.stderr)
                return 2
        else:
            try:
                res = call_chat(model=MODEL, system=SYSTEM_PROMPT,
                                user=user_prompt, max_tokens=5000)
                model_label = MODEL
            except OpenRouterError as e:
                print(f"OPENROUTER FAILED: {e}", file=sys.stderr)
                return 2
        content = res["content"].strip()
        if content.startswith("```"):
            content = content.split("```", 2)[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        try:
            ai_json = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"AI returned malformed JSON: {e}", file=sys.stderr)
            print(f"---first 500 chars---\n{content[:500]}", file=sys.stderr)
            return 3
        usage = res.get("usage", {})

    # 5. Merge AI exegesis into readings
    payload = {
        "schemaVersion": 1,
        "date": args.date,
        "liturgical": liturgical,
        "saint": None,
        "readings": [
            {**r, "exegesis": ai_json["readings"][i].get("exegesis", {})}
            for i, r in enumerate(readings)
        ],
        "synthesis": ai_json.get("synthesis", {"title": "", "body": ""}),
        "generation": {
            "model": model_label,
            "promptTokens": usage.get("prompt_tokens", 0),
            "completionTokens": usage.get("completion_tokens", 0),
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "corpusVersion": CORPUS_VERSION,
        }
    }

    # 6. Validate (only in live mode - dry runs have empty CCC refs which is fine)
    if not args.dry_run:
        try:
            validate(payload, ccc_path=ROOT / "corpus" / "embeddings" / "ccc.parquet")
        except ValidationError as e:
            print(f"VALIDATION FAILED: {e}", file=sys.stderr)
            # Save the bad output for inspection
            (out_path.parent / f"{args.date}.invalid.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            return 4

    # 7. Write
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0

def _write_placeholder(out_path: Path, iso_date: str, reason: str) -> None:
    out_path.write_text(json.dumps({
        "schemaVersion": 1, "date": iso_date, "status": reason
    }, indent=2), encoding="utf-8")

def _scrape_via_claude(iso_date: str) -> list[dict]:
    """Delegate the day's reading fetch to Claude CLI's WebFetch tool.

    Used when local Python `requests` is blocked (e.g., Geo-IP firewalls
    that block UK-hosted Universalis from US campus networks). Claude's
    WebFetch routes through Anthropic's network so it bypasses the local
    restriction.

    Returns a list of reading dicts in the same shape as parse_readings()
    would produce. Empty list on failure.
    """
    yyyymmdd = iso_date.replace("-", "")
    url = f"https://universalis.com/europe.usa/{yyyymmdd}/mass.htm"
    prompt = f"""Use your WebFetch tool to fetch {url}

Parse the HTML and return ONLY a JSON array (no markdown fences, no
commentary, just the JSON) of the daily Mass readings. Each entry:

{{
  "kind": "first_reading" | "psalm" | "second_reading" | "gospel",
  "title": "First reading" | "Responsorial Psalm" | "Second reading" | "Gospel",
  "citation": "Acts 1:12-14",
  "text": "the full reading text",
  "translation": "Universalis (US)",
  "refrain": "for psalm only, the antiphon line"
}}

Skip 'Gospel Acclamation' entries (not used). Include 'second_reading' only
if present (Sundays + solemnities). Return JSON array starting with [ and
ending with ]. NOTHING ELSE."""

    try:
        res = call_claude_cli(system="You are a precise web scraper.",
                              user=prompt, timeout=180)
    except ClaudeCliError as e:
        print(f"  claude WebFetch call failed: {e}", file=sys.stderr)
        return []
    content = res["content"].strip()
    # Strip markdown fences if Claude wrapped output despite instructions
    if content.startswith("```"):
        content = content.split("```", 2)[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    # Extract the JSON array if there's preamble
    start = content.find("[")
    end = content.rfind("]")
    if start >= 0 and end > start:
        content = content[start:end + 1]
    try:
        readings = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"  claude WebFetch returned non-JSON: {e}", file=sys.stderr)
        print(f"  ---first 500 chars---\n{content[:500]}", file=sys.stderr)
        return []
    if not isinstance(readings, list) or not readings:
        print(f"  claude WebFetch returned empty/invalid array", file=sys.stderr)
        return []
    return readings

if __name__ == "__main__":
    sys.exit(main())
