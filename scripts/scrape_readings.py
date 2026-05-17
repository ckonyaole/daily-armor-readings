"""Scrape Universalis daily Mass readings (US edition).

URL pattern: ``https://universalis.com/europe.usa/YYYYMMDD/mass.htm``

Universalis is free for personal / non-commercial use per their published
terms. This module replaces the previous USCCB scraper, which was blocked by
a JavaScript proof-of-work challenge that prevented unattended automation.

DOM structure (as of 2026 snapshots)::

    <table class="each">                  one per reading section
      <tr><th>First reading</th><th>Acts 1:12-14</th></tr>
    </table>
    <h4>...short summary...</h4>          optional
    <div class="p">paragraph 1</div>      prose body for first/second/gospel
    <div class="p">paragraph 2</div>
    ...
    <hr class="shortrule">                may or may not be present

For the Responsorial Psalm the body is structured as verse lines instead of
``div.p`` paragraphs:

    <div class="v">refrain text</div>     first refrain (always non-gb)
    <div class="v">or</div>               optional alternate marker
    <div class="v">Alleluia!</div>        optional alternate refrain
    <div class="v gb">refrain restated</div>   per-strophe restatement (gb)
    <div class="v">stanza line 1</div>
    <div class="vi">stanza line 2 (indented)</div>
    ...

Section headings we keep: First reading, Responsorial Psalm, Second reading,
Gospel. Skipped: Gospel Acclamation, "Or:" alternate acclamations.
"""
from __future__ import annotations

import re
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag


class ScrapeError(Exception):
    """Raised when scraping or parsing fails."""


USER_AGENT = (
    "daily-armor-readings/1.0 "
    "(Catholic devotional research; +https://github.com/ckonyaole/daily-armor-readings)"
)
BASE = "https://universalis.com/europe.usa"
TRANSLATION = "Universalis (US)"

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def date_to_path(d: str) -> str:
    """Convert ISO date 'YYYY-MM-DD' to Universalis path slug 'YYYYMMDD'."""
    if not isinstance(d, str):
        raise ScrapeError(f"bad date format (want YYYY-MM-DD): {d!r}")
    m = _DATE_RE.match(d)
    if not m:
        raise ScrapeError(f"bad date format (want YYYY-MM-DD): {d!r}")
    return f"{m.group(1)}{m.group(2)}{m.group(3)}"


def fetch_day(date_str: str) -> str:
    """Fetch the raw HTML for a given Universalis daily-Mass page.

    ``date_str`` is an ISO ``YYYY-MM-DD`` string. We convert internally to
    Universalis's URL slug so callers always speak ISO dates.
    """
    path = date_to_path(date_str)
    url = f"{BASE}/{path}/mass.htm"
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
        # Universalis serves UTF-8 but sometimes omits the charset header.
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = "utf-8"
        return r.text
    except requests.RequestException as e:
        raise ScrapeError(f"fetch failed {url}: {e}") from e


# --- parsing -----------------------------------------------------------------

_LABEL_MAP = {
    "first reading": "first_reading",
    "second reading": "second_reading",
    "responsorial psalm": "psalm",
    "gospel": "gospel",
}

_SKIP_LABELS = {"gospel acclamation", "or:", "or"}


def parse_readings(html: str) -> dict:
    """Parse Universalis HTML into a structured dict.

    Returns::

        {"readings": [
            {"kind", "title", "citation", "text", "translation", "refrain"?},
            ...
        ]}

    Raises ``ScrapeError`` when the input is empty or no reading sections are
    discovered (likely indicating a DOM change or a block page).
    """
    if not html or not html.strip():
        raise ScrapeError("empty html")

    soup = BeautifulSoup(html, "html.parser")
    section_tables = soup.find_all("table", class_="each")
    if not section_tables:
        raise ScrapeError(
            "no reading sections found (expected <table class='each'> — "
            "Universalis DOM may have changed or this is a block page)"
        )

    readings: list[dict] = []
    for idx, table in enumerate(section_tables):
        label, citation = _parse_section_header(table)
        if label is None:
            continue
        kind = _classify_kind(label)
        if kind is None:
            continue

        next_stop = section_tables[idx + 1] if idx + 1 < len(section_tables) else None
        body_nodes = _collect_body_nodes(table, next_stop)

        if kind == "psalm":
            text, refrain = _render_psalm(body_nodes)
        else:
            text = _render_prose(body_nodes)
            refrain = None

        if not text or len(text) < 20:
            # Don't add half-empty sections — surface as a parse failure if
            # nothing else lands either.
            continue

        entry: dict = {
            "kind": kind,
            "title": label,
            "citation": citation,
            "text": text,
            "translation": TRANSLATION,
        }
        if kind == "psalm" and refrain:
            entry["refrain"] = refrain
        readings.append(entry)

    if not readings:
        raise ScrapeError(
            "no readings parsed — Universalis DOM may have changed "
            "(expected <table class='each'> headers with following div.p / div.v body)"
        )
    return {"readings": readings}


# --- helpers -----------------------------------------------------------------

def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _parse_section_header(table: Tag) -> tuple[Optional[str], str]:
    """Return (label, citation) from a Universalis <table class="each"> header.

    Returns (None, "") if the table doesn't look like a section header.
    """
    ths = table.find_all("th")
    if len(ths) < 1:
        return None, ""
    label = _clean(ths[0].get_text(" ", strip=True))
    citation = _clean(ths[1].get_text(" ", strip=True)) if len(ths) >= 2 else ""
    return label, citation


def _classify_kind(label: str) -> Optional[str]:
    """Map a section label like 'First reading' to a canonical kind, or None."""
    key = label.lower().strip().rstrip(":")
    if key in _SKIP_LABELS:
        return None
    if "gospel acclamation" in key:
        return None
    # Exact-prefix match against the label map.
    for prefix, kind in _LABEL_MAP.items():
        if key == prefix or key.startswith(prefix + " "):
            return kind
    # "Gospel" alone (e.g., heading is just 'Gospel') and Universalis sometimes
    # uses 'The Gospel'. Match last to avoid swallowing 'Gospel Acclamation'.
    if "gospel" in key and "acclamation" not in key:
        return "gospel"
    return None


def _collect_body_nodes(start: Tag, stop: Optional[Tag]) -> list[Tag]:
    """Collect sibling tag nodes between ``start`` and ``stop`` (exclusive)."""
    out: list[Tag] = []
    cur = start.next_sibling
    while cur is not None and cur is not stop:
        if isinstance(cur, Tag):
            out.append(cur)
        cur = cur.next_sibling
    return out


def _render_prose(nodes: list[Tag]) -> str:
    """Join prose paragraphs (div.p) into a newline-separated text block.

    Also accepts div.v / div.vi for gospels where Universalis sometimes
    formats Jesus' words as verse-style lines (e.g., the Sunday Gospel
    of John 17 in our fixture).
    """
    paragraphs: list[str] = []
    for n in nodes:
        if n.name == "h4":
            # Skip the short editorial summary heading
            continue
        if n.name == "div":
            cls = n.get("class") or []
            if "p" in cls:
                txt = _clean(n.get_text(" ", strip=True))
                if txt:
                    paragraphs.append(txt)
            elif "v" in cls or "vi" in cls:
                txt = _clean(n.get_text(" ", strip=True))
                if txt:
                    paragraphs.append(txt)
            elif "audioclip" in cls or "podcastentry" in cls:
                continue
        # tables, hrs, etc. are ignored
    return "\n".join(paragraphs).strip()


def _render_psalm(nodes: list[Tag]) -> tuple[str, str]:
    """Render a responsorial psalm body, returning (text, refrain).

    Universalis lays out the psalm as:
      div.v          -> primary refrain (first non-gb div.v)
      div.v "or"     -> separator
      div.v          -> alternate refrain (e.g. 'Alleluia!')
      div.v.gb       -> refrain restated as strophe header (bold/gray)
      div.v / div.vi -> stanza lines
      div.v.gb       -> refrain restated
      ...
    """
    lines: list[str] = []
    refrain = ""
    refrain_locked = False

    for n in nodes:
        if not isinstance(n, Tag) or n.name != "div":
            continue
        cls = n.get("class") or []
        if "audioclip" in cls or "podcastentry" in cls:
            continue
        if "v" not in cls and "vi" not in cls:
            continue

        txt = _clean(n.get_text(" ", strip=True))
        if not txt:
            continue

        # The first div.v that is NOT marked 'gb' and not an 'or'/'Alleluia'
        # separator is the canonical refrain.
        if not refrain_locked and "v" in cls and "gb" not in cls:
            low = txt.lower().rstrip("!.,")
            if low not in ("or", "alleluia"):
                refrain = txt
                refrain_locked = True

        lines.append(txt)

    text = "\n".join(lines).strip()
    return text, refrain
