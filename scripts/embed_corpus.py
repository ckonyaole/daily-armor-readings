"""Chunk Catena Aurea + CCC, embed with sentence-transformers, write parquet.

Run once per corpus update. Output committed to repo for use by retrieve.py.

Catena format observations (cf. corpus/catena_aurea/*.txt):
- Each chapter starts with two lines: 'CHAP' and '. N' (split by the source HTML).
- Verse markers appear on their own line as 'N:N' or 'N:N-M' (with hyphen,
  en-dash, or em-dash).  In matthew.txt the first chapter uses 'Ver. 1.' on
  the gospel-text line, but the consistent machine-readable anchor is the
  'N:N' line that precedes every commentary block.
- Each commentary chunk starts with an ALL-CAPS Father name on its own line
  (e.g. 'CHRYSOSTOM', 'PSEUDO-AUGUSTINE') followed by a line that begins with
  '. ' carrying the work reference and the commentary text.
- The Father attribution may be followed by additional continuation lines.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).parent.parent
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# --- Catena chunking ---------------------------------------------------------

# Verse marker line: '1:1', '1:2-3', '1:2–3', '1:2—3' (hyphen, en-dash, em-dash)
_VERSE_RE = re.compile(r"^(\d{1,3}):(\d{1,3})(?:[\-‐‑‒–—―](\d{1,3}))?$")
# 'Ver. N.' or 'Vv. N-M.' style — used in matthew chapter 1 + a couple of other spots.
_VER_RE = re.compile(r"^Ver(?:s)?\.?\s+(\d{1,3})(?:[\-‐‑‒–—―](\d{1,3}))?\.")
# All-caps Father name on its own line. Allow letters, dashes, spaces, apostrophes.
# Length cap avoids matching long all-caps sentences. Min length 3 skips 'A', 'B'.
_FATHER_RE = re.compile(r"^[A-Z][A-Z\s\-'.&]{2,49}$")
# Lines we should never treat as a Father (chapter headers, index junk, etc.)
_FATHER_BLOCKLIST = {
    "CHAP", "HOME", "SUMMA", "PRAYERS", "FATHERS", "CLASSICS", "CONTACT",
    "CATHOLIC ENCYCLOPEDIA", "FATHERS OF THE CHURCH", "RCIA", "VOCATIONS",
    "SAINTS", "SOCIAL DOCTRINE", "CATHOLIC JOBS",
}


def _is_father_line(line: str, next_line: str | None) -> bool:
    """A Father attribution is an all-caps short line whose next non-empty
    sibling begins with '.' (the period that introduces the work + text)."""
    if line in _FATHER_BLOCKLIST:
        return False
    if not _FATHER_RE.match(line):
        return False
    if next_line is None:
        return False
    return next_line.startswith(".")


def chunk_catena(gospel: str, raw: str) -> list[dict]:
    lines = raw.splitlines()
    n = len(lines)
    chunks: list[dict] = []

    chapter = 0
    verse_start = 0
    verse_end = 0
    current_father: str | None = None
    current_work: str | None = None
    current_text: list[str] = []

    def flush() -> None:
        nonlocal current_text, current_father, current_work
        if current_father and current_text and chapter > 0 and verse_start > 0:
            text = " ".join(current_text).strip()
            text = re.sub(r"\s+", " ", text)
            if len(text) > 80:  # skip stubs
                chunks.append({
                    "gospel": gospel,
                    "chapter": chapter,
                    "verseStart": verse_start,
                    "verseEnd": verse_end or verse_start,
                    "father": current_father,
                    "work": current_work or "",
                    "text": text,
                })
        current_text = []
        current_father = None
        current_work = None

    def next_nonempty(idx: int) -> str | None:
        j = idx + 1
        while j < n and not lines[j].strip():
            j += 1
        return lines[j].strip() if j < n else None

    i = 0
    while i < n:
        raw_line = lines[i]
        line = raw_line.strip()
        if not line:
            i += 1
            continue

        # CHAP header (split across two lines).
        if line == "CHAP" and i + 1 < n:
            # Look ahead for '. N' line (skipping blanks).
            nxt = next_nonempty(i)
            m_chap = re.match(r"^\.\s*(\d+)", nxt or "")
            if m_chap:
                flush()
                chapter = int(m_chap.group(1))
                verse_start = verse_end = 0
                # Skip past the '. N' line.
                # advance i to the line containing '. N'
                j = i + 1
                while j < n and not lines[j].strip():
                    j += 1
                i = j + 1
                continue
        # Combined 'CHAP. N' single line — defensive.
        m_chap1 = re.match(r"^CHAP\.\s*(\d+)$", line)
        if m_chap1:
            flush()
            chapter = int(m_chap1.group(1))
            verse_start = verse_end = 0
            i += 1
            continue

        # Verse marker (N:N or N:N-M).
        m_verse = _VERSE_RE.match(line)
        if m_verse and chapter > 0 and int(m_verse.group(1)) == chapter:
            flush()
            verse_start = int(m_verse.group(2))
            verse_end = int(m_verse.group(3)) if m_verse.group(3) else verse_start
            i += 1
            continue
        # 'Ver. N.' fallback (only seen in matthew ch.1 and a couple of stray spots).
        m_ver = _VER_RE.match(line)
        if m_ver:
            flush()
            verse_start = int(m_ver.group(1))
            verse_end = int(m_ver.group(2)) if m_ver.group(2) else verse_start
            # Don't 'continue' — the line itself contains gospel text we just skip.
            i += 1
            continue

        # Father attribution.
        nxt = next_nonempty(i)
        if _is_father_line(line, nxt):
            flush()
            current_father = line.title()  # normalise case
            # Next non-empty line begins with '. (work) text...'
            # Walk to next non-empty line and parse it.
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n:
                body = lines[j].strip()
                # Strip leading '. '
                body = body[1:].lstrip() if body.startswith(".") else body
                m_work = re.match(r"^\(([^)]+)\)\s*(.*)$", body)
                if m_work:
                    current_work = m_work.group(1).strip()
                    rest = m_work.group(2).strip()
                else:
                    current_work = None
                    rest = body
                if rest:
                    current_text.append(rest)
                i = j + 1
                continue
            i += 1
            continue

        # Plain text continuation of current commentary.
        if current_father:
            current_text.append(line)
        i += 1

    flush()
    return chunks


# --- CCC chunking ------------------------------------------------------------

_CCC_LINE_RE = re.compile(r"^\s*(\d{1,4})\s+(.+)$")


def chunk_ccc(part_n: int, raw: str) -> list[dict]:
    chunks: list[dict] = []
    current_n = 0
    current_buf: list[str] = []

    def flush() -> None:
        nonlocal current_n, current_buf
        if current_n > 0 and current_buf:
            text = re.sub(r"\s+", " ", " ".join(current_buf)).strip()
            if len(text) > 30:
                chunks.append({
                    "part": part_n,
                    "paragraph": current_n,
                    "section": "",
                    "text": text,
                })
        current_buf = []

    for line in raw.splitlines():
        m = _CCC_LINE_RE.match(line)
        if m and 1 <= int(m.group(1)) <= 2865:
            flush()
            current_n = int(m.group(1))
            current_buf = [m.group(2).strip()]
        elif current_n > 0 and line.strip():
            current_buf.append(line.strip())
    flush()
    return chunks


# --- Main --------------------------------------------------------------------

def main() -> int:
    print(f"Loading embedder: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)
    out_dir = ROOT / "corpus" / "embeddings"
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Catena ---
    print("\n--- CATENA ---")
    catena_chunks: list[dict] = []
    for gospel in ["matthew", "mark", "luke", "john"]:
        path = ROOT / "corpus" / "catena_aurea" / f"{gospel}.txt"
        if not path.exists():
            print(f"missing {path}", file=sys.stderr)
            return 1
        text = path.read_text(encoding="utf-8")
        gc = chunk_catena(gospel, text)
        print(f"  {gospel}: {len(gc)} chunks")
        catena_chunks.extend(gc)
    print(f"Total Catena chunks: {len(catena_chunks)}")
    if len(catena_chunks) < 1000:
        print("ABORT: Catena chunk count is suspiciously low.", file=sys.stderr)
        return 2

    print("Embedding Catena (this takes a few minutes)...")
    texts = [c["text"] for c in catena_chunks]
    embs = model.encode(
        texts, batch_size=64, show_progress_bar=True,
        convert_to_numpy=True, normalize_embeddings=True,
    )
    df = pd.DataFrame(catena_chunks)
    df["embedding"] = list(embs)
    df["id"] = df.apply(
        lambda r: (
            f"catena.{r['gospel']}.{r['chapter']}.{r['verseStart']}."
            f"{r['father'].lower().replace(' ', '_').replace('.', '').replace(chr(0x2019), '')}"
        ),
        axis=1,
    )
    out = out_dir / "catena.parquet"
    df.to_parquet(out)
    print(f"Wrote {out} ({out.stat().st_size:,} bytes)")

    # --- CCC ---
    print("\n--- CCC ---")
    ccc_chunks: list[dict] = []
    for n in [1, 2, 3, 4]:
        path = ROOT / "corpus" / "ccc" / f"part_{n}.txt"
        text = path.read_text(encoding="utf-8")
        cc = chunk_ccc(n, text)
        print(f"  part_{n}: {len(cc)} chunks")
        ccc_chunks.extend(cc)
    print(f"Total CCC chunks: {len(ccc_chunks)}")
    if len(ccc_chunks) < 2500:
        print(
            f"WARNING: CCC chunk count is {len(ccc_chunks)}, expected ~2865",
            file=sys.stderr,
        )

    print("Embedding CCC...")
    texts = [c["text"] for c in ccc_chunks]
    embs = model.encode(
        texts, batch_size=64, show_progress_bar=True,
        convert_to_numpy=True, normalize_embeddings=True,
    )
    df = pd.DataFrame(ccc_chunks)
    df["embedding"] = list(embs)
    df["id"] = df["paragraph"].apply(lambda p: f"ccc.{p}")
    out = out_dir / "ccc.parquet"
    df.to_parquet(out)
    print(f"Wrote {out} ({out.stat().st_size:,} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
