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
                       retrieved_per_reading: list[dict],
                       with_skills: bool = False) -> str:
    """Assemble the user-turn prompt.

    Args:
        readings: list of {"kind", "title", "citation", "text", "refrain"?}
        liturgical: {"title", "season", "week", "rank", "color",
                     "lectionaryCycle"?, "weekdayCycle"?, "date"?}
        saint: optional {"name", "rank", "bio"?}
        retrieved_per_reading: parallel to readings; each is
                               {"catena": [...], "ccc": [...]}
        with_skills: when True, the prompt also instructs Claude to invoke
                     the 4 Catholic skills (bible-entry-icb,
                     step-2-reading-bible, rosary-mysteries-guide,
                     with-him) and return their results as additional
                     top-level fields. Only set this when running via
                     Claude CLI where the Skill tool is available.
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

    if with_skills:
        parts.append(_SKILL_INSTRUCTIONS)
    else:
        parts.append(_BASE_INSTRUCTIONS)
    return "\n".join(parts)


_BASE_INSTRUCTIONS = """
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
"""


_SKILL_INSTRUCTIONS = """
## Required JSON output

You have access to four installed Catholic skills. After generating the base
exegesis, invoke each skill on today's GOSPEL passage and include the results
as additional top-level fields. Return EVERYTHING in one JSON object with
this exact shape (schemaVersion 2):

{
  "schemaVersion": 2,
  "readings": [
    {
      "kind": "first_reading" | "psalm" | "second_reading" | "gospel",
      "exegesis": {
        "summary": "string — 2-4 sentences explaining what this reading proclaims",
        "patristicQuotes": [{"father": "...", "work": "...", "quote": "..."}],
        "cccReferences": [{"paragraph": <int>, "title": "short label"}],
        "thematicConnection": "string — how this reading relates to today's other readings"
      }
    }
  ],
  "synthesis": {
    "title": "What today's readings say together",
    "body": "string — 150-250 words weaving all readings into one message"
  },
  "bibleEntry": {
    "_source": "bible-entry-icb skill",
    "questions": [
      "10 scene-entry questions (one per array element) covering: setting, "
      "characters, emotions, tension, what Jesus might be feeling, God's "
      "heart in this passage, where you locate yourself in the story, "
      "one moment that catches your attention, how this connects to "
      "another part of the Gospel, one truth to carry."
    ]
  },
  "gospelImmersion": {
    "_source": "step-2-reading-bible skill (Fr. Mike Schmitz Ignatian method)",
    "icbParaphrase": "string — today's Gospel rewritten in ICB-simple English (~3-5 short sentences)",
    "senses": {
      "sight": "string — what you SEE in the scene (~30-60 words)",
      "sound": "string — what you HEAR (~30-60 words)",
      "touch": "string — what you FEEL physically (~30-60 words)",
      "smell": "string — what you SMELL (~30-60 words)",
      "taste": "string — what you TASTE, if applicable; else 'not present in this scene' (~30-60 words)"
    },
    "jesusMoment": "string — describe Jesus in the scene from your imagined vantage point: face, posture, eyes, voice, one specific thing He does (~80-120 words)"
  },
  "rosaryTieIn": {
    "_source": "rosary-mysteries-guide skill",
    "mysterySet": "Joyful" | "Sorrowful" | "Glorious" | "Luminous",
    "reasonForToday": "string — why this set fits today (day-of-week default or feast override; ~30 words)",
    "spiritualFruit": "string — the spiritual fruit of this mystery set (1 short sentence)",
    "connectionToGospel": "string — 2 sentences linking today's Gospel to this mystery set's themes"
  },
  "walkWithHim": {
    "_source": "with-him skill (Catholic companionship mode)",
    "modeDetected": "morning" | "midday" | "evening",
    "companionPrompt": "string — 80-120 words written AS IF to Christ as a daily companion, framed for the detected time-of-day mode. First-person, intimate, no third-person 'Jesus' references — speak directly TO Him.",
    "oneTruthToCarry": "string — one short, memorable sentence the user can take into the rest of their day"
  }
}

IMPORTANT:
- For the skill-augmented sections, USE the corresponding installed skill via
  the Skill tool. Do NOT fabricate skill output. If a skill fails to invoke,
  omit that section entirely (better to skip than to fake).
- The order of readings in the output MUST match the order in the input above.
- All four skill sections are OPTIONAL — if you cannot invoke a skill for any
  reason, omit that key. The app gracefully handles missing fields.
- Return ONE JSON object with EVERYTHING. No markdown fences, no commentary.
"""


def build_examen_prompt(today: dict, yesterday: dict | None = None) -> str:
    """Build the Claude Opus prompt for tonight's Evening Examen.

    today: the morning's already-generated TODAY payload dict (must include
           date, liturgical, readings, optionally walkWithHim).
    yesterday: optional dict with keys 'resolution' and 'mood' from
               yesterday's completed Examen. When None, continuity is
               omitted (sync-OFF tier or first night).

    Returns a single prompt string designed to invoke the `with-him` skill
    (Evening Examen mode) and the `bible-entry-icb` skill on today's gospel,
    producing a JSON object matching the ExamenScaffold schema.
    """
    gospel = next((r for r in today.get('readings', [])
                   if r.get('kind') == 'gospel'), None)
    gospel_citation = gospel.get('citation', "today's Gospel") if gospel else ''
    walk = today.get('walkWithHim') or {}
    one_truth = walk.get('oneTruthToCarry', '')

    continuity_block = ''
    if yesterday and yesterday.get('resolution'):
        resolution = yesterday['resolution']
        mood = yesterday.get('mood', 'neutral')
        continuity_block = f"""
CONTINUITY (last night):
Yesterday you resolved: "{resolution}"
Yesterday's mood was: {mood}

In Station 3 (Review) and Station 4 (Sorrow), gently reference how this
resolution may have lived in today. Never preach. Never shame.
"""

    return f"""You are guiding a faithful Catholic into tonight's Examination of
Conscience using the with-him skill (Evening Examen mode) and the
bible-entry-icb skill anchored on {gospel_citation}.

TODAY'S LITURGICAL CONTEXT:
- Date: {today['date']}
- Title: {today['liturgical']['title']}
- Season: {today['liturgical']['season']}
- Rank: {today['liturgical']['rank']}
- Color: {today['liturgical']['color']}

TODAY'S GOSPEL:
{gospel['text'] if gospel else '(no gospel)'}

WALK-WITH-HIM CARRY:
{one_truth or '(none generated)'}
{continuity_block}
TASK:
Generate the 5-station Examen scaffold as a single JSON object. Each
station is a personalized prompt grounded in today's gospel and the
with-him companion text. Use the bible-entry-icb skill internally to
ensure the gospel anchor is alive in the prompts.

Required JSON shape:
{{
  "openingPrayer": "<one-paragraph prayer to begin>",
  "stations": [
    {{"kind": "gratitude", "title": "Gratitude",
      "prompt": "<80-150 word personalized prompt>",
      "scriptureAnchor": "<optional verse>",
      "silenceSeconds": 60}},
    {{"kind": "petition", "title": "Petition",
      "prompt": "<80-150 words>", "silenceSeconds": 30}},
    {{"kind": "review", "title": "Review the Day",
      "prompt": "<120-200 words - longest station>",
      "silenceSeconds": 90}},
    {{"kind": "sorrow", "title": "Sorrow",
      "prompt": "<80-150 words, gentle, never shaming>",
      "silenceSeconds": 60}},
    {{"kind": "renewal", "title": "Renewal",
      "prompt": "<80-150 words pointing toward tomorrow>",
      "silenceSeconds": 60}}
  ],
  "closing": "<one-paragraph closing, ~60 words, 'carry this into sleep' tone>"
}}

Output ONLY the JSON object, no markdown fences, no preamble."""
