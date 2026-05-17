# Daily Armor Readings

Daily Catholic Mass reading exegesis pipeline for the
[My Daily Armor](https://github.com/ckonyaole/my-daily-armor) Android app.

A GitHub Action runs at 04:00 UTC every day. It:

1. Scrapes the day's readings from [Universalis](https://universalis.com) (US edition)
2. Retrieves relevant patristic commentary (Catena Aurea) + Catechism
   paragraphs from a locally-embedded vector DB
3. Calls Claude Opus 4.7 via OpenRouter to generate a theological exegesis
4. Validates the output (schema + CCC paragraph existence)
5. Commits the result to `output/<date>.json`

The My Daily Armor Flutter app fetches these JSON files via
`raw.githubusercontent.com` (the repo is public so no auth is needed).

## Setup

```
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
cp .env.example .env  # add your OPENROUTER_API_KEY
```

## Run locally

```
python scripts/generate.py --date 2026-05-17
```

## Corpus licenses

- **Catena Aurea** (Aquinas) — public domain (Newman 1841 translation)
- **Catechism of the Catholic Church** — © Libreria Editrice Vaticana 1994, 1997;
  used here for educational and devotional purposes per their published terms
- **Daily Mass readings** — sourced from [Universalis](https://universalis.com)
  US edition; free for personal/non-commercial use per their published terms
  (USCCB previously used, but they now block bot traffic with a JS PoW challenge)
- Code — MIT
