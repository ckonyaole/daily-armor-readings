"""Assemble the Opus 4.7 prompt for daily Catholic exegesis."""
from __future__ import annotations

SYSTEM_PROMPT = """You are a faithful Catholic theologian writing a daily \
exegesis of the Mass readings for a US Catholic audience. Your output MUST \
be valid JSON matching the schema described below.

DOCTRINAL GUARDRAILS (non-negotiable):

1. You are rooted in the Magisterium of the Roman Catholic Church. Never \
present Protestant interpretations as equivalent to Catholic teaching. When \
a passage has a contested reading (e.g., the Eucharist, Marian doctrines, \
papal authority, justification), give the Catholic interpretation as \
authoritative.

2. Every theological claim must be grounded in (a) Sacred Scripture, (b) the \
provided Catena Aurea quotes, or (c) the provided Catechism paragraphs. Do \
NOT invent saint quotations or CCC paragraph numbers. If you reference a \
Father, copy from the provided context; you may lightly modernize phrasing \
for readability but never alter meaning.

3. CCC references in your output must ONLY use paragraph numbers from the \
provided context. Never cite a CCC paragraph not explicitly provided.

4. The 'thematicConnection' for each reading should identify how the Church \
intentionally paired it with the other readings of the day.

5. The 'synthesis' should weave all readings into one coherent message about \
what the Church proclaims today.

6. Write in clear, devout, contemplative English. This is for prayer, not a \
seminary lecture.

7. If today is a Solemnity, Feast, or Triduum day, acknowledge its weight.

Return ONLY a JSON object. No markdown fences, no commentary outside the JSON.
"""

def build_user_prompt(*, readings: list[dict], liturgical: dict,
                       saint: dict | None,
                       retrieved_per_reading: list[dict]) -> str:
    """Assemble the user-turn prompt.

    Args:
        readings: list of {"kind", "title", "citation", "text", "refrain"?}
        liturgical: {"title", "season", "week", "rank", "color",
                     "lectionaryCycle"?, "weekdayCycle"?, "date"?}
        saint: optional {"name", "rank", "bio"?}
        retrieved_per_reading: parallel to readings; each is
                               {"catena": [...], "ccc": [...]}
    """
    parts: list[str] = []
    parts.append(f"# Today: {liturgical.get('title', '')}")
    if liturgical.get("date"):
        parts.append(f"Date: {liturgical['date']}")
    parts.append(f"Season: {liturgical.get('season', '')}, "
                  f"{liturgical.get('week', '')}")
    parts.append(f"Rank: {liturgical.get('rank', '')}, "
                  f"Liturgical color: {liturgical.get('color', '')}")
    cycle = liturgical.get("lectionaryCycle") or liturgical.get("weekdayCycle")
    if cycle:
        parts.append(f"Lectionary cycle: {cycle}")

    if saint:
        parts.append(f"\nSaint of the day: {saint.get('name', '')} "
                      f"({saint.get('rank', '')})")
        if saint.get("bio"):
            parts.append(f"  {saint['bio']}")

    parts.append("\n## Readings\n")
    for i, (reading, retrieved) in enumerate(zip(readings, retrieved_per_reading)):
        parts.append(f"### {reading.get('title', '')} — "
                      f"{reading.get('citation', '')}\n")
        parts.append(reading.get("text", ""))
        if reading.get("refrain"):
            parts.append(f"\nRefrain: {reading['refrain']}")
        catena = retrieved.get("catena", [])
        if catena:
            parts.append("\n#### Retrieved patristic commentary:")
            for q in catena:
                parts.append(f"- {q['father']} ({q.get('work', '')}): "
                              f"{q['quote']}")
        ccc = retrieved.get("ccc", [])
        if ccc:
            parts.append("\n#### Retrieved Catechism paragraphs:")
            for c in ccc:
                parts.append(f"- CCC {c['paragraph']}: {c['text']}")
        parts.append("")  # blank line between readings

    parts.append("""
## Required JSON output

Return ONLY a JSON object with this exact shape:

{
  "readings": [
    {
      "kind": "first_reading" | "psalm" | "second_reading" | "gospel",
      "exegesis": {
        "summary": "string — 2-4 sentences explaining what this reading proclaims",
        "patristicQuotes": [
          {"father": "...", "work": "...", "quote": "..."}
        ],
        "cccReferences": [
          {"paragraph": <int>, "title": "short label"}
        ],
        "thematicConnection": "string — how this reading relates to today's other readings"
      }
    }
  ],
  "synthesis": {
    "title": "What today's readings say together",
    "body": "string — 150-250 words weaving all readings into one message"
  }
}

The order of readings in the output MUST match the order in the input above.
""")
    return "\n".join(parts)
