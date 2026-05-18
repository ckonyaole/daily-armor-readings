"""Debug: fetch a Universalis URL and print structure so we can adapt the scraper."""
from __future__ import annotations
import argparse
import sys
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "daily-armor-readings/1.0 (Catholic devotional research)"}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYYMMDD")
    parser.add_argument("--edition", default="europe.usa",
                        help="Universalis edition path (default europe.usa)")
    args = parser.parse_args()
    url = f"https://universalis.com/{args.edition}/{args.date}/mass.htm"
    print(f"=== FETCH: {url} ===")
    r = requests.get(url, timeout=30, headers=HEADERS)
    print(f"=== STATUS: {r.status_code} ===")
    if r.encoding == "ISO-8859-1" or not r.encoding:
        r.encoding = "utf-8"
    html = r.text
    print(f"=== LENGTH: {len(html):,} chars ===")

    soup = BeautifulSoup(html, "html.parser")
    # Print all H1 + H2 (likely page title + Mass type)
    print("\n=== HEADINGS ===")
    for h in soup.find_all(["h1", "h2"])[:20]:
        print(f"  {h.name}: {h.get_text(strip=True)[:120]}")

    # Find all table.each (the existing scraper's target)
    tables = soup.select("table.each")
    print(f"\n=== TABLE.EACH count: {len(tables)} ===")
    for i, t in enumerate(tables):
        ths = t.find_all("th")
        print(f"  [{i}] {len(ths)} <th>:")
        for j, th in enumerate(ths[:3]):
            print(f"        th[{j}]: {th.get_text(strip=True)[:80]}")

    # Look for ANY content matching "Acts 1:1" or "Acts 1:12"
    print("\n=== ACTS REFERENCES IN TEXT ===")
    text = soup.get_text("\n")
    for line in text.splitlines():
        if "Acts" in line and ("1:" in line or "19:" in line):
            print(f"  {line.strip()[:120]}")
            if line.count("Acts") > 3:
                break

    return 0

if __name__ == "__main__":
    sys.exit(main())
