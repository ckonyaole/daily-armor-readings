"""Scrape USCCB daily Mass readings.

URL pattern: https://bible.usccb.org/bible/readings/MMDDYY.cfm

DOM structure (as of 2024 wayback snapshots):

  div#block-usccb-readings-content
    div.b-verse                   <- one per reading section
      div.content-header          <- "Reading 1 Acts 10:25..."
      div.address                 <- "Acts 10:25-26, 34-35, 44-48"
      div.content-body            <- reading text
      (psalms include "R. (cf. 2b) <refrain>" markers)
"""
from __future__ import annotations

import re
from typing import Optional

import requests
from bs4 import BeautifulSoup


class ScrapeError(Exception):
    """Raised when scraping or parsing fails."""


USER_AGENT = (
    "daily-armor-readings/1.0 "
    "(Catholic devotional research; +https://github.com/ckonyaole/daily-armor-readings)"
)
BASE = "https://bible.usccb.org/bible/readings"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def date_to_path(d: str) -> str:
    """Convert ISO date 'YYYY-MM-DD' to USCCB path slug 'MMDDYY'."""
    if not isinstance(d, str) or not _DATE_RE.match(d):
        raise ScrapeError(f"bad date format (want YYYY-MM-DD): {d!r}")
    yyyy, mm, dd = d.split("-")
    return f"{mm}{dd}{yyyy[2:]}"


def fetch_day(mmddyy: str) -> str:
    """Fetch the raw HTML for a given USCCB readings page."""
    url = f"{BASE}/{mmddyy}.cfm"
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
        return r.text
    except requests.RequestException as e:
        raise ScrapeError(f"fetch failed {url}: {e}") from e


def parse_readings(html: str) -> dict:
    """Parse USCCB readings HTML into a structured dict.

    Returns:
        {"readings": [{"kind", "title", "citation", "text", "translation", "refrain?"}, ...]}
    """
    if not html or not html.strip():
        raise ScrapeError("empty html")

    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.select("div.b-verse")
    readings: list[dict] = []

    for block in blocks:
        header_el = block.find(class_="content-header")
        addr_el = block.find(class_="address")
        body_el = block.find(class_="content-body")

        title = _clean(header_el.get_text(" ", strip=True)) if header_el else ""
        citation = _clean(addr_el.get_text(" ", strip=True)) if addr_el else ""
        text = body_el.get_text("\n", strip=True) if body_el else ""

        kind = _classify_kind(title)
        if kind is None:
            # Skip Alleluia / Gospel Acclamation / unknown sections
            continue
        if not text:
            continue

        entry: dict = {
            "kind": kind,
            "title": title,
            "citation": citation,
            "text": text,
            "translation": "NABRE",
        }
        if kind == "psalm":
            entry["refrain"] = _extract_refrain(text)
        readings.append(entry)

    if not readings:
        raise ScrapeError(
            "no readings parsed — USCCB DOM may have changed "
            "(expected div.b-verse with content-header/address/content-body)"
        )
    return {"readings": readings}


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _classify_kind(title: str) -> Optional[str]:
    """Map a section heading to a canonical reading kind.

    Returns None for sections we skip (Alleluia, Gospel Acclamation, etc.).
    """
    t = title.lower().strip()
    # Drop trailing citation so we don't confuse e.g. "Gospel Acclamation Jn..."
    head = t.split(" ", 2)
    head2 = " ".join(head[:2]) if len(head) >= 2 else t

    if "gospel acclamation" in t or t.startswith("alleluia") or t.startswith("verse before"):
        return None
    if "first reading" in t or head2 in ("reading 1", "reading i"):
        return "first_reading"
    if "responsorial psalm" in t or t.startswith("psalm "):
        return "psalm"
    if "second reading" in t or head2 in ("reading 2", "reading ii"):
        return "second_reading"
    if "gospel" in t:
        return "gospel"
    return None


def _extract_refrain(text: str) -> str:
    """Pull the responsorial refrain out of a psalm body.

    USCCB serves refrains as a leading marker line ('R.' or 'R. (cf. 2b)') followed
    by the refrain text on the next line(s), then either 'or:' (variant refrain) or
    the verse stanza. We walk lines and collect text after each R. until we hit
    a separator or another R. marker. Prefer the first non-Alleluia refrain.
    """
    candidates: list[str] = []
    lines = [ln.strip() for ln in text.splitlines()]
    i = 0
    while i < len(lines):
        ln = lines[i]
        # Match a refrain marker line: "R.", "R. (cf. 2b)", "℟.", "Response:"
        m = re.match(r"^(?:R\.|℟\.|Response:)\s*(\([^)]+\))?\s*(.*)$", ln)
        if m:
            buf = [m.group(2).strip()] if m.group(2) else []
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt:
                    j += 1
                    continue
                if re.match(r"^(?:R\.|℟\.|Response:|or:)\s*", nxt):
                    break
                # Stop if line looks like the start of a verse stanza (capital + no terminal punctuation)
                buf.append(nxt)
                # Refrains end at a period — if this line ends with one, stop
                if nxt.endswith("."):
                    j += 1
                    break
                j += 1
            cand = " ".join(buf).strip().rstrip(".").strip()
            if cand:
                candidates.append(cand)
            i = j
            continue
        i += 1

    for c in candidates:
        if c.lower() not in ("alleluia", "alleluia, alleluia"):
            return c
    return candidates[0] if candidates else ""
