"""Schema validation for Evening Examen scaffold output."""
from __future__ import annotations

EXPECTED_STATION_KINDS = ['gratitude', 'petition', 'review', 'sorrow', 'renewal']


class ExamenValidationError(Exception):
    pass


def validate_examen(scaffold: dict) -> None:
    """Raises ExamenValidationError on schema problems."""
    stations = scaffold.get('stations')
    if not isinstance(stations, list):
        raise ExamenValidationError('stations must be a list')
    if len(stations) != 5:
        raise ExamenValidationError(
            f'must have exactly 5 stations, got {len(stations)}')
    for i, (got, expected) in enumerate(zip(stations, EXPECTED_STATION_KINDS)):
        kind = got.get('kind')
        if kind != expected:
            raise ExamenValidationError(
                f'station {i} order: expected {expected}, got {kind}')
        prompt = (got.get('prompt') or '').strip()
        if not prompt:
            raise ExamenValidationError(f'station {i} ({kind}) prompt is empty')
        if not isinstance(got.get('silenceSeconds'), (int, float)):
            raise ExamenValidationError(
                f'station {i} ({kind}) silenceSeconds must be a number')
    if not (scaffold.get('openingPrayer') or '').strip():
        raise ExamenValidationError('openingPrayer is empty')
    if not (scaffold.get('closing') or '').strip():
        raise ExamenValidationError('closing is empty')
