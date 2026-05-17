from pathlib import Path
import pandas as pd
import numpy as np
import pytest
from scripts.retrieve import Retriever, CorpusLoadError

ROOT = Path(__file__).parent.parent
REAL_CATENA = ROOT / "corpus" / "embeddings" / "catena.parquet"
REAL_CCC = ROOT / "corpus" / "embeddings" / "ccc.parquet"

def _fake_corpus(tmp_path):
    """Build a tiny fixture corpus for fast tests using real embeddings."""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    catena_rows = [
        {"id": "catena.john.14.23.augustine", "gospel": "john",
         "chapter": 14, "verseStart": 23, "verseEnd": 23,
         "father": "St. Augustine", "work": "Tractates on John, 76",
         "text": "We must understand that the Father and the Son come to "
                 "those who love them not by moving from place to place, "
                 "but by manifesting themselves to those they enter."},
        {"id": "catena.matthew.5.3.chrysostom", "gospel": "matthew",
         "chapter": 5, "verseStart": 3, "verseEnd": 3,
         "father": "St. John Chrysostom", "work": "Homilies on Matthew",
         "text": "Blessed are the poor in spirit, meaning the humble of heart."},
        {"id": "catena.john.14.23.aquinas", "gospel": "john",
         "chapter": 14, "verseStart": 23, "verseEnd": 23,
         "father": "St. Thomas Aquinas", "work": "Catena on John",
         "text": "The Father and the Son make their dwelling in the soul "
                 "through love, an indwelling more intimate than any "
                 "physical presence."},
        {"id": "catena.john.14.23.cyril", "gospel": "john",
         "chapter": 14, "verseStart": 23, "verseEnd": 23,
         "father": "St. Cyril of Alexandria", "work": "Commentary on John",
         "text": "Christ leaves his peace as inheritance to those who love him."},
    ]
    embs = model.encode([r["text"] for r in catena_rows],
                          normalize_embeddings=True, convert_to_numpy=True)
    df = pd.DataFrame(catena_rows)
    df["embedding"] = list(embs)
    catena = tmp_path / "catena.parquet"
    df.to_parquet(catena)

    ccc_rows = [
        {"id": "ccc.260", "paragraph": 260, "part": 1, "section": "",
         "text": "The ultimate end of the whole divine economy is the entry "
                 "of God's creatures into the perfect unity of the Blessed "
                 "Trinity, called to be a dwelling for the Most Holy Trinity."},
        {"id": "ccc.729", "paragraph": 729, "part": 1, "section": "",
         "text": "Only when the hour has arrived for his glorification does "
                 "Jesus promise the coming of the Holy Spirit."},
        {"id": "ccc.1969", "paragraph": 1969, "part": 3, "section": "",
         "text": "The New Law practices the acts of religion: almsgiving, "
                 "prayer, and fasting, directing them to the Father who sees "
                 "in secret."},
    ]
    embs2 = model.encode([r["text"] for r in ccc_rows],
                          normalize_embeddings=True, convert_to_numpy=True)
    df2 = pd.DataFrame(ccc_rows)
    df2["embedding"] = list(embs2)
    ccc = tmp_path / "ccc.parquet"
    df2.to_parquet(ccc)
    return catena, ccc

# --- fixture-corpus tests (fast, deterministic) ---

def test_retrieves_relevant_catena(tmp_path):
    catena, ccc = _fake_corpus(tmp_path)
    r = Retriever(catena_path=catena, ccc_path=ccc)
    hits = r.retrieve_catena(
        "the Father and Son dwell in the soul of those who love them",
        k=3, gospel="john")
    assert len(hits) >= 2
    # Top hit should be from John 14 commentary (Augustine, Aquinas, or Cyril)
    assert hits[0]["father"] in ("St. Augustine", "St. Thomas Aquinas",
                                  "St. Cyril of Alexandria")

def test_gospel_filter(tmp_path):
    catena, ccc = _fake_corpus(tmp_path)
    r = Retriever(catena_path=catena, ccc_path=ccc)
    hits = r.retrieve_catena("blessed", k=5, gospel="john")
    assert all(h.get("_gospel") == "john" for h in hits)

def test_dedup_per_father(tmp_path):
    catena, ccc = _fake_corpus(tmp_path)
    r = Retriever(catena_path=catena, ccc_path=ccc)
    hits = r.retrieve_catena("Father Son indwelling love", k=10,
                              gospel="john", max_per_father=1)
    fathers = [h["father"] for h in hits]
    assert len(fathers) == len(set(fathers))

def test_ccc_retrieves_relevant(tmp_path):
    catena, ccc = _fake_corpus(tmp_path)
    r = Retriever(catena_path=catena, ccc_path=ccc)
    hits = r.retrieve_ccc("Trinity dwells in soul of those in grace", k=2)
    assert hits[0]["paragraph"] == 260

def test_corrupted_corpus_raises():
    with pytest.raises(CorpusLoadError):
        Retriever(catena_path="/nonexistent.parquet", ccc_path="/nonexistent.parquet")

def test_empty_query_returns_empty(tmp_path):
    catena, ccc = _fake_corpus(tmp_path)
    r = Retriever(catena_path=catena, ccc_path=ccc)
    assert r.retrieve_catena("", k=3) == []

# --- real-corpus smoke test ---

@pytest.mark.skipif(not REAL_CATENA.exists() or not REAL_CCC.exists(),
                     reason="real corpus not embedded yet")
def test_real_corpus_retrieves_john_14_for_indwelling_query():
    r = Retriever(catena_path=str(REAL_CATENA), ccc_path=str(REAL_CCC))
    hits = r.retrieve_catena(
        "whoever loves me will keep my word and my Father will love him "
        "and we will come to him and make our dwelling with him",
        k=8, gospel="john")
    # At least one hit should be from John chapter 14 (where this verse lives)
    chapters = {h.get("_chapter") for h in hits}
    assert 14 in chapters, f"expected John 14 in top-k chapters: {chapters}"
