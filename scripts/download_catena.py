"""Download Catena Aurea (Newman 1841 translation) into corpus/catena_aurea/.

Source: eCatholic2000.com hosts the full Newman translation as one chapter per
shtml page. The TOC at /catena/index.shtml maps chapters to numeric URLs.
We fetch each chapter's HTML, strip nav/script chrome, and concatenate.

The Catena Aurea is public domain (Newman's translation, 1841).
"""
from __future__ import annotations
from pathlib import Path
import re
import sys
import time
import requests
from bs4 import BeautifulSoup

BASE = "https://www.ecatholic2000.com/catena/"

# Chapter -> shtml number ranges, derived from index.shtml TOC.
# Matthew 1-28 = untitled-08..untitled-35
# Mark    1-16 = untitled-41..untitled-56
# Luke    1-24 = untitled-62..untitled-85
# John    1-21 = untitled-89..untitled-109
GOSPELS: dict[str, list[int]] = {
    "matthew": list(range(8, 36)),    # 28 chapters: 08..35
    "mark":    list(range(41, 57)),   # 16 chapters: 41..56
    "luke":    list(range(62, 86)),   # 24 chapters: 62..85
    "john":    list(range(89, 110)),  # 21 chapters: 89..109
}

OUT = Path(__file__).parent.parent / "corpus" / "catena_aurea"
HEADERS = {"User-Agent": "daily-armor-readings/1.0 (Catholic devotional research)"}


def fetch(url: str) -> str | None:
    try:
        r = requests.get(url, timeout=60, headers=HEADERS)
        r.raise_for_status()
        # eCatholic2000 sends "text/html" with no charset; requests falls back to
        # ISO-8859-1 which mojibakes the embedded UTF-8 smart quotes. Force UTF-8.
        r.encoding = "utf-8"
        return r.text
    except requests.RequestException as e:
        print(f"  ! {e}", file=sys.stderr)
        return None


def to_plain_text(html: str) -> str:
    """Strip nav chrome and return paragraph text only."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "nav", "header", "footer", "form"]):
        t.decompose()
    # eCatholic2000 wraps content; drop common chrome by simple text rules
    text = soup.get_text("\n")
    # Collapse 3+ blank lines, strip excess whitespace per line
    lines = [ln.rstrip() for ln in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def fetch_gospel(gospel: str, chapter_nums: list[int]) -> str:
    chunks: list[str] = []
    for n in chapter_nums:
        url = f"{BASE}untitled-{n:02d}.shtml"
        print(f"    {url}")
        html = fetch(url)
        if not html:
            continue
        chunks.append(to_plain_text(html))
        time.sleep(0.4)  # be kind
    return "\n\n".join(chunks)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    for gospel, chapters in GOSPELS.items():
        out = OUT / f"{gospel}.txt"
        print(f"Fetching {gospel} ({len(chapters)} chapters)...")
        text = fetch_gospel(gospel, chapters)
        if text and len(text) > 100_000:
            out.write_text(text, encoding="utf-8")
            print(f"  -> wrote {len(text):,} chars")
        else:
            print(f"  ! thin result ({len(text or '')} chars)", file=sys.stderr)
            failed.append(gospel)
    if failed:
        print(f"FAILED: {failed}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
