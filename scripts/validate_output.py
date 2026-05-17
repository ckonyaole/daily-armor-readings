"""Schema + corpus-grounding validation for daily output JSON."""
from __future__ import annotations
from pathlib import Path
import pandas as pd

CURRENT_SCHEMA = 1
REQUIRED_TOP = {"schemaVersion", "date", "liturgical", "readings",
                "synthesis", "generation"}
VALID_KINDS = {"first_reading", "psalm", "second_reading", "gospel"}

class ValidationError(Exception):
    pass

_CCC_CACHE: dict[str, set[int]] = {}
def _load_valid_ccc(path) -> set[int]:
    key = str(path)
    if key not in _CCC_CACHE:
        df = pd.read_parquet(path)
        _CCC_CACHE[key] = set(int(p) for p in df["paragraph"].tolist())
    return _CCC_CACHE[key]

def validate(payload: dict, *, ccc_path) -> None:
    """Raises ValidationError on terminal issues; prints warnings for soft issues."""
    missing = REQUIRED_TOP - set(payload.keys())
    if missing:
        raise ValidationError(f"missing top-level fields: {sorted(missing)}")
    if payload["schemaVersion"] != CURRENT_SCHEMA:
        raise ValidationError(
            f"schemaVersion must be {CURRENT_SCHEMA}, got {payload['schemaVersion']}")
    readings = payload.get("readings") or []
    if not readings:
        raise ValidationError("readings must not be empty")
    syn = payload.get("synthesis") or {}
    if not (syn.get("body") or "").strip():
        raise ValidationError("synthesis.body must not be empty")
    valid_ccc = _load_valid_ccc(ccc_path)
    for i, r in enumerate(readings):
        if r.get("kind") not in VALID_KINDS:
            raise ValidationError(
                f"readings[{i}].kind invalid: {r.get('kind')}")
        ex = r.get("exegesis") or {}
        for j, ref in enumerate(ex.get("cccReferences", [])):
            try:
                p = int(ref["paragraph"])
            except (KeyError, ValueError, TypeError):
                raise ValidationError(
                    f"readings[{i}].cccReferences[{j}]: malformed paragraph")
            if p not in valid_ccc:
                raise ValidationError(
                    f"readings[{i}].cccReferences[{j}]: "
                    f"CCC paragraph {p} does not exist")
        for j, q in enumerate(ex.get("patristicQuotes", [])):
            if not (q.get("father") or "").strip():
                print(f"warning: readings[{i}].patristicQuotes[{j}] "
                       f"missing father attribution")
