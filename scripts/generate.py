"""Daily orchestrator: scrape -> retrieve -> prompt -> call -> validate -> write."""
from __future__ import annotations
import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

from scripts.scrape_readings import fetch_day, parse_readings, ScrapeError
from scripts.retrieve import Retriever
from scripts.prompt_template import SYSTEM_PROMPT, build_user_prompt
from scripts.call_openrouter import call_chat, OpenRouterError
from scripts.validate_output import validate, ValidationError
from scripts.liturgical import season_for, lectionary_cycle, weekday_cycle

ROOT = Path(__file__).parent.parent
MODEL = "anthropic/claude-opus-4-7"
CORPUS_VERSION = "v1.0"

def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--out", default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="skip OpenRouter call; write debug stub")
    parser.add_argument("--fixture", default=None,
                        help="Path to fixture HTML to use instead of live fetch")
    args = parser.parse_args(argv)

    d = date.fromisoformat(args.date)
    out_path = Path(args.out) if args.out else ROOT / "output" / f"{args.date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Scrape (or load fixture)
    try:
        if args.fixture:
            html = Path(args.fixture).read_text(encoding="utf-8")
        else:
            html = fetch_day(args.date)
        scraped = parse_readings(html)
    except (ScrapeError, FileNotFoundError) as e:
        _write_placeholder(out_path, args.date, f"scrape_failed: {e}")
        print(f"SCRAPE FAILED: {e}", file=sys.stderr)
        return 1
    readings = scraped["readings"]

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
    else:
        try:
            res = call_chat(model=MODEL, system=SYSTEM_PROMPT,
                            user=user_prompt, max_tokens=5000)
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
            "model": MODEL,
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

if __name__ == "__main__":
    sys.exit(main())
