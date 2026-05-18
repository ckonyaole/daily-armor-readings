"""Fetch a Bible passage by citation from a public Catholic-friendly source.

Used by generate.py when an override specifies explicit citations instead of
trusting Universalis's date-based reading lookup.

Sources tried in order:
1. biblegateway.com with RSV-CE (RSV Catholic Edition, free for personal use)
2. Universalis's per-passage URL pattern as fallback
"""
from __future__ import annotations
import re
import sys
import urllib.parse
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "daily-armor-readings/1.0 (Catholic devotional research)"}

class PassageFetchError(Exception):
    pass

def fetch_biblegateway(citation: str, version: str = "RSVCE") -> str:
    """Fetch a passage from biblegateway.com and return plain text."""
    q = urllib.parse.quote(citation)
    url = f"https://www.biblegateway.com/passage/?search={q}&version={version}&interface=print"
    try:
        r = requests.get(url, timeout=30, headers=HEADERS)
        r.raise_for_status()
    except requests.RequestException as e:
        raise PassageFetchError(f"biblegateway fetch failed: {e}") from e
    soup = BeautifulSoup(r.text, "html.parser")
    # Strip footnote markers, cross-refs, version tags
    for sel in [".footnote", ".crossreference", ".chapternum", ".versenum",
                ".small-caps", "sup", ".footnotes", ".crossrefs", ".publisher-info"]:
        for el in soup.select(sel):
            el.decompose()
    # Main passage text is in .passage-text
    container = soup.select_one(".passage-text") or soup.select_one(".result-text-style-normal")
    if not container:
        raise PassageFetchError(f"biblegateway: no passage-text found for {citation}")
    text = container.get_text("\n", strip=True)
    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 30:
        raise PassageFetchError(f"biblegateway: passage too short ({len(text)} chars)")
    return text

def fetch(citation: str) -> str:
    """Try sources in order; raise PassageFetchError if all fail."""
    errors: list[str] = []
    try:
        return fetch_biblegateway(citation)
    except PassageFetchError as e:
        errors.append(f"biblegateway: {e}")
    raise PassageFetchError(f"all sources failed for '{citation}': {'; '.join(errors)}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: fetch_bible_passage.py 'Acts 1:1-11'", file=sys.stderr)
        sys.exit(2)
    citation = sys.argv[1]
    try:
        text = fetch(citation)
        print(f"=== {citation} ({len(text)} chars) ===")
        print(text)
    except PassageFetchError as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)
