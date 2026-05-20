"""Generate tonight's Evening Examen scaffold via Claude CLI."""
from __future__ import annotations
import json
from datetime import datetime, timezone

from scripts.call_claude_cli import call_cli as call_claude_cli, ClaudeCliError
from scripts.prompt_template import build_examen_prompt

EXAMEN_SYSTEM = """You are a Catholic spiritual director versed in the
Ignatian Examination of Conscience. You speak with the gentleness of a
confessor, the precision of a theologian, and the warmth of a friend.

You have access to two installed skills:
- `with-him`: Catholic companionship skill (Evening Examen mode)
- `bible-entry-icb`: Guided Bible pre-reading framework

When generating tonight's Examen scaffold, invoke both skills internally.
The output is a single JSON object matching the schema specified by the user.
Output ONLY the JSON, no markdown fences."""


def generate(today: dict, yesterday: dict | None = None) -> dict:
    """Generate the Examen payload for tonight.

    Returns: {
        'scaffold': {...},
        'generatedAt': iso8601,
        'model': 'claude-code-cli/subscription',
        'continuityUsed': bool,
    }
    """
    user_prompt = build_examen_prompt(today, yesterday=yesterday)
    res = call_claude_cli(system=EXAMEN_SYSTEM, user=user_prompt, timeout=120)
    content = res['content'].strip()
    if content.startswith('```'):
        content = content.split('```', 2)[1]
        if content.startswith('json'):
            content = content[4:]
        content = content.strip()
    scaffold = json.loads(content)
    return {
        'scaffold': scaffold,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'model': 'claude-code-cli/subscription',
        'continuityUsed': yesterday is not None,
    }
