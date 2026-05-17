"""Download Catechism of the Catholic Church from the Vatican IntraText edition.

Source: https://www.vatican.va/archive/ENG0015/_INDEX.HTM (official Vatican)
(c) Libreria Editrice Vaticana 1994/1997. Used here for personal/educational/
devotional purposes (paragraph-level citation in AI-generated exegesis) which
is within the publisher's stated terms.

The IntraText edition splits the CCC across ~374 subsection HTML pages
(__P1.HTM ... __PAE.HTM). Each subsection contains <p class=MsoNormal> blocks
where numbered paragraphs begin with the paragraph number on its own line:

    <p class=MsoNormal>279
    "In the beginning God created..." ...</p>

We fetch every subsection, extract paragraph-number / body pairs, then bucket
into the 4 canonical parts.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

OUT = Path(__file__).parent.parent / "corpus" / "ccc"
BASE = "https://www.vatican.va/archive/ENG0015/"
INDEX = BASE + "_INDEX.HTM"
HEADERS = {"User-Agent": "daily-armor-readings/1.0 (Catholic devotional research)"}

PART_BOUNDARIES = [
    ("part_1", 1, 1065),
    ("part_2", 1066, 1690),
    ("part_3", 1691, 2557),
    ("part_4", 2558, 2865),
]


def fetch(url: str, retries: int = 3) -> str | None:
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=60, headers=HEADERS, verify=False)
            r.raise_for_status()
            # Vatican IntraText pages are iso-8859-1
            r.encoding = "iso-8859-1"
            return r.text
        except requests.RequestException as e:
            if attempt == retries - 1:
                print(f"  ! fetch failed for {url}: {e}", file=sys.stderr)
                return None
            time.sleep(2 ** attempt)
    return None


def get_subsection_urls(index_html: str) -> list[str]:
    """Extract all __PXX.HTM links from the table of contents."""
    pages = re.findall(r'href=(__P[A-Z0-9]+\.HTM)', index_html, flags=re.IGNORECASE)
    seen: list[str] = []
    s = set()
    for p in pages:
        if p not in s:
            s.add(p)
            seen.append(p)
    return seen


def extract_paragraphs_from_page(html: str) -> dict[int, str]:
    """Parse one IntraText subsection page. Returns {paragraph_number: body}.

    The Vatican IntraText pages mostly use:
        <p class=MsoNormal>279
        body text...</p>
    but occasionally split across consecutive <p> tags so a number ends up
    mid-paragraph:
        <p>...Decalogue. 2077 The</p><p>gift of the Decalogue...</p>
    To capture both shapes we concatenate all MsoNormal blocks into one
    flowing text and then run a single greedy regex.
    """
    soup = BeautifulSoup(html, "html.parser")
    # Remove footnote markers' sup tags so they don't break text flow
    for sup in soup.find_all("sup"):
        sup.decompose()

    chunks: list[str] = []
    for p in soup.find_all("p", class_="MsoNormal"):
        text = p.get_text(" ", strip=True)
        if text:
            chunks.append(text)
    if not chunks:
        return {}
    flow = " \n ".join(chunks)
    flow = re.sub(r"\s+", " ", flow).strip()

    paragraphs: dict[int, str] = {}
    # Greedy: each numbered paragraph eats text up to the next number-in-range.
    pattern = re.compile(r'(?<!\d)(\d{1,4})\s+(.*?)(?=(?<!\d)\d{1,4}\s|\Z)', re.DOTALL)
    for m in pattern.finditer(flow):
        n = int(m.group(1))
        if not (1 <= n <= 2865):
            continue
        body = m.group(2).strip(" .,;")
        body = re.sub(r"\s+", " ", body).strip()
        if len(body) < 10:
            continue
        if n in paragraphs and len(paragraphs[n]) >= len(body):
            continue
        paragraphs[n] = body
    return paragraphs


def assemble_parts(paragraphs: dict[int, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, start, end in PART_BOUNDARIES:
        lines = []
        for n in sorted(p for p in paragraphs if start <= p <= end):
            lines.append(f"{n} {paragraphs[n]}")
        out[name] = "\n\n".join(lines)
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    print(f"Fetching index: {INDEX}")
    index_html = fetch(INDEX)
    if not index_html:
        print("FAILED: cannot reach Vatican IntraText index", file=sys.stderr)
        return 1

    urls = get_subsection_urls(index_html)
    print(f"Found {len(urls)} subsection pages")

    all_paragraphs: dict[int, str] = {}
    for i, page in enumerate(urls, 1):
        if i % 25 == 0 or i == len(urls):
            print(f"  [{i}/{len(urls)}] fetched so far -> {len(all_paragraphs)} paragraphs")
        html = fetch(BASE + page)
        if not html:
            continue
        page_paras = extract_paragraphs_from_page(html)
        for n, body in page_paras.items():
            # Prefer first occurrence (later pages occasionally re-reference)
            if n not in all_paragraphs:
                all_paragraphs[n] = body
        time.sleep(0.15)  # polite to vatican.va

    print(f"\nTotal paragraphs extracted: {len(all_paragraphs):,}")
    if len(all_paragraphs) < 2500:
        print(
            f"WARNING: expected ~2865 paragraphs, got {len(all_paragraphs)}",
            file=sys.stderr,
        )

    parts = assemble_parts(all_paragraphs)
    for name, body in parts.items():
        out = OUT / f"{name}.txt"
        out.write_text(body, encoding="utf-8")
        print(f"  -> {name}.txt: {len(body):,} chars")

    if all(parts[n] for n in ["part_1", "part_2", "part_3", "part_4"]):
        return 0
    print("FAILED: at least one part is empty", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
