"""Liturgical calendar helpers."""
from __future__ import annotations
from datetime import date, timedelta

def easter_date(year: int) -> date:
    """Anonymous Gregorian (Meeus/Jones/Butcher) algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)

def first_advent_sunday(year: int) -> date:
    """Sunday nearest Nov 30."""
    nov30 = date(year, 11, 30)
    weekday = nov30.weekday()  # Monday=0 ... Sunday=6
    if weekday == 6:
        return nov30
    diff = 6 - weekday
    if diff > 3:
        diff -= 7
    return nov30 + timedelta(days=diff)

def lectionary_cycle(d: date) -> str:
    """Sunday cycle A/B/C — based on liturgical year (starts 1st Sunday of Advent).
    Year A is divisible by 3, B remainder 1, C remainder 2 (per USCCB convention).
    Returns one of 'A', 'B', 'C'."""
    advent_this_year = first_advent_sunday(d.year)
    liturgical_year = d.year + 1 if d >= advent_this_year else d.year
    return ["A", "B", "C"][(liturgical_year - 1) % 3]

def weekday_cycle(d: date) -> str:
    """Weekday 1st-reading cycle I (odd liturgical year) / II (even).
    Liturgical year starts 1st Sunday of Advent."""
    advent_this_year = first_advent_sunday(d.year)
    liturgical_year = d.year + 1 if d >= advent_this_year else d.year
    return "I" if liturgical_year % 2 == 1 else "II"

def season_for(d: date) -> tuple[str, str]:
    """Returns (season_name, liturgical_color)."""
    e = easter_date(d.year)
    ash_wed = e - timedelta(days=46)
    pentecost = e + timedelta(days=49)
    christmas = date(d.year, 12, 25)
    epiphany = date(d.year, 1, 6)
    advent = first_advent_sunday(d.year)

    # Baptism of the Lord — Sunday after Epiphany (or Monday if Epiphany Sun)
    days_to_sun = (6 - epiphany.weekday()) % 7
    baptism_of_lord = epiphany + timedelta(days=days_to_sun or 7)

    if d >= advent and d < christmas:
        return ("Advent", "purple")
    if d >= christmas and d <= date(d.year, 12, 31):
        return ("Christmas", "white")
    if d <= baptism_of_lord:
        return ("Christmas", "white")
    if d >= ash_wed and d < e:
        return ("Lent", "purple")
    if d >= e and d < pentecost:
        return ("Easter", "white")
    if d == pentecost:
        return ("Easter", "red")
    return ("Ordinary Time", "green")
