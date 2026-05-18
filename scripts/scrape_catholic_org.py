"""Catholic.org daily readings scraper — US-hosted fallback for Universalis.

Used when Universalis (UK-hosted) is unreachable from the local network
(e.g., Dillard.edu's Geo-IP firewall blocks UK IPs). Catholic.org is in
US data centers and serves the same Roman lectionary readings.

URL pattern: https://www.catholic.org/bible/daily_reading/?select_date=YYYY-MM-DD

DOM structure (May 2026 snapshot):

    <div id="drReadings">
      <h3>Reading 1, <em>Acts 19:1-8</em></h3>
      <p><sup>1</sup>verse text</p>
      <p><sup>2</sup>verse text</p>
      ...
      <h3>Responsorial Psalm, <em>Psalms 68:2-3, 4-5, 6-7</em></h3>
      <p>...</p>
      <h3>Reading 2, <em>...</em></h3>     (only on Sundays/feasts)
      <p>...</p>
    </div>
    <h3>Gospel, <em>John 16:29-33</em></h3>   (sometimes outside drReadings)
    <p>...</p>

Quirks:
- The Gospel h3 sometimes lives OUTSIDE the #drReadings container — we
  search the whole document for h3s with the canonical labels.
- `<sup>` verse numbers are stripped during text extraction.
- Catholic.org embeds anchor links to its own glossary; we keep the text
  but drop the link wrappers.
- No explicit refrain marker for the psalm — we treat the first paragraph
  as the refrain candidate (best-effort).
"""
from __future__ import annotations

import re
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag

from scripts.scrape_readings import ScrapeError  # reuse exception type

USER_AGENT = (
    "daily-armor-readings/1.0 "
    "(Catholic devotional research; +https://github.com/ckonyaole/daily-armor-readings)"
)
BASE = "https://www.catholic.org/bible/daily_reading/"
TRANSLATION = "Catholic.org (NJB-based)"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_LABEL_MAP = {
    "reading 1": "first_reading",
    "first reading": "first_reading",
    "reading 2": "second_reading",
    "second reading": "second_reading",
    "responsorial psalm": "psalm",
    "psalm": "psalm",
    "gospel": "gospel",
}

_SKIP_LABELS = {
    "gospel acclamation",
    "verse before the gospel",
    "alleluia",
}


def fetch_day(date_str: str) -> str:
    """Fetch the raw HTML for a given catholic.org daily-reading page."""
    if not isinstance(date_str, str) or not _DATE_RE.match(date_str):
        raise ScrapeError(f"bad date format (want YYYY-MM-DD): {date_str!r}")
    url = f"{BASE}?select_date={date_str}"
    try:
        r = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        r.raise_for_status()
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = "utf-8"
        return r.text
    except requests.RequestException as e:
        raise ScrapeError(f"fetch failed {url}: {e}") from e


def parse_readings(html: str) -> dict:
    """Parse a catholic.org daily-reading page into the same dict shape that
    scrape_readings.parse_readings produces."""
    if not html or not html.strip():
        raise ScrapeError("empty html")

    soup = BeautifulSoup(html, "html.parser")

    # Find the daily-reading container; everything we want comes from this
    # subtree (h3s inside or directly following it).
    container = soup.find("div", id="drReadings")
    if not container:
        raise ScrapeError(
            "no #drReadings container — catholic.org DOM may have changed"
        )

    # Collect h3 nodes that look like reading section headers. We anchor
    # on h3s containing <em>...</em> with a Bible-like citation. We accept
    # h3s inside #drReadings as well as h3s that appear shortly AFTER it
    # (Gospel sometimes lives outside).
    candidates = _collect_section_h3s(soup, container)

    readings: list[dict] = []
    for idx, h3 in enumerate(candidates):
        label, citation = _parse_h3(h3)
        if label is None:
            continue
        kind = _classify_kind(label)
        if kind is None:
            continue
        next_stop = candidates[idx + 1] if idx + 1 < len(candidates) else None
        body_paras = _collect_paragraphs(h3, next_stop)
        text = _render_paragraphs(body_paras)
        if not text or len(text) < 20:
            continue

        entry: dict = {
            "kind": kind,
            "title": label,
            "citation": citation,
            "text": text,
            "translation": TRANSLATION,
        }
        if kind == "psalm":
            entry["refrain"] = _extract_psalm_refrain(body_paras)
        readings.append(entry)

    if not readings:
        raise ScrapeError(
            "no readings parsed from catholic.org — DOM may have changed"
        )
    return {"readings": readings}


# --- helpers -----------------------------------------------------------------

def _collect_section_h3s(soup: BeautifulSoup, container: Tag) -> list[Tag]:
    """Return h3 nodes that look like reading-section headers (have <em>)."""
    out: list[Tag] = []
    # Order matters: collect in document order so paragraph collection
    # via "next sibling until next h3" works.
    for h3 in soup.find_all("h3"):
        em = h3.find("em")
        if not em:
            continue
        # Skip h3s that are clearly navigation (e.g., "Reading for May 17th")
        # those have anchor links wrapping the text
        if h3.find("a") and "Reading for" in h3.get_text(" ", strip=True):
            continue
        out.append(h3)
    return out


def _parse_h3(h3: Tag) -> tuple[Optional[str], str]:
    """Extract (label, citation) from <h3>Label, <em>Citation</em></h3>."""
    em = h3.find("em")
    citation = _clean(em.get_text(" ", strip=True)) if em else ""
    # Label is the part before the <em> (and the trailing comma)
    label_text = h3.get_text(" ", strip=True)
    if em:
        em_text = em.get_text(" ", strip=True)
        # Remove the em text from the label, then strip trailing comma/space
        idx = label_text.rfind(em_text)
        if idx >= 0:
            label_text = label_text[:idx]
    label = _clean(label_text).rstrip(",").strip()
    if not label:
        return None, citation
    return label, citation


def _classify_kind(label: str) -> Optional[str]:
    key = label.lower().strip().rstrip(":")
    if key in _SKIP_LABELS:
        return None
    if "gospel acclamation" in key or "alleluia" in key:
        return None
    for prefix, kind in _LABEL_MAP.items():
        if key == prefix or key.startswith(prefix + " "):
            return kind
    return None


def _collect_paragraphs(h3: Tag, stop_h3: Optional[Tag]) -> list[Tag]:
    """Walk forward from h3 collecting <p> tags until we hit stop_h3 or end."""
    out: list[Tag] = []
    cur = h3
    while True:
        cur = cur.find_next(["p", "h3"])
        if cur is None:
            break
        if cur is stop_h3:
            break
        if cur.name == "h3":
            # Hit another header before our stop — different section started
            break
        if cur.name == "p":
            out.append(cur)
    return out


def _render_paragraphs(paras: list[Tag]) -> str:
    """Join paragraph text, stripping <sup>verse-num</sup> markers and
    anchor wrappers but preserving readable prose."""
    lines: list[str] = []
    for p in paras:
        # Remove sup tags (verse numbers)
        for sup in p.find_all("sup"):
            sup.decompose()
        txt = _clean(p.get_text(" ", strip=True))
        if txt:
            lines.append(txt)
    return "\n".join(lines).strip()


def _extract_psalm_refrain(paras: list[Tag]) -> str:
    """Best-effort psalm refrain extraction.

    Catholic.org doesn't mark the refrain explicitly. Heuristic: the first
    short line (≤120 chars) that contains an exclamation, the word
    'Lord' / 'God', or 'Alleluia' is a refrain candidate.

    Falls back to the first paragraph's first sentence if no good match.
    """
    if not paras:
        return ""
    for p in paras[:3]:
        for sup in p.find_all("sup"):
            sup.decompose()
        text = _clean(p.get_text(" ", strip=True))
        if 0 < len(text) <= 120 and (
            "!" in text or "lord" in text.lower() or "alleluia" in text.lower()
        ):
            return text
    first = _clean(paras[0].get_text(" ", strip=True))
    # Strip leading <sup>N</sup> remnants if decompose() didn't catch them
    first = re.sub(r"^\d+\s*", "", first)
    sentence = re.split(r"(?<=[.!?])\s+", first, maxsplit=1)[0]
    return sentence[:120] if sentence else ""


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()
