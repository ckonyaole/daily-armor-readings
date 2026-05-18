"""Shell out to Claude Code CLI in headless mode.

Uses the user's Pro/Max subscription auth (flat rate, no API key needed).
Drop-in alternative to `call_openrouter.call_chat` — same return shape.

Requires `claude` CLI to be on PATH and signed in interactively at least once.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

class ClaudeCliError(Exception):
    pass

def call_cli(*, system: str, user: str,
             dangerously_skip_permissions: bool = True,
             timeout: int = 300) -> dict:
    """Invoke `claude --print` with the given system + user prompts.

    Returns {"content": str, "usage": {...}} mirroring call_openrouter.call_chat.

    Strategy: combine system + user into one stdin payload (Claude Code's
    --print mode reads the full prompt as one user-turn message; we prefix
    with the system rules at the top).
    """
    claude = shutil.which("claude") or shutil.which("claude.cmd")
    if not claude:
        raise ClaudeCliError(
            "`claude` CLI not on PATH. Install with `npm install -g @anthropic-ai/claude-code` "
            "and sign in interactively once.")

    # Build the combined prompt. The "SYSTEM RULES" prefix gives the
    # equivalent of a system message in a single user-turn input.
    full_prompt = (
        "=== SYSTEM RULES (follow strictly) ===\n"
        + system.strip()
        + "\n=== END SYSTEM RULES ===\n\n"
        + user.strip()
    )

    # Write to a temp file so we don't hit Windows CMD line-length limits
    # piping massive prompts via stdin.
    tmp = NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                              encoding="utf-8")
    try:
        tmp.write(full_prompt)
        tmp.flush()
        tmp.close()

        cmd = [claude, "--print", "--output-format", "text"]
        if dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")

        try:
            with open(tmp.name, "r", encoding="utf-8") as fh:
                result = subprocess.run(
                    cmd, stdin=fh, capture_output=True, text=True,
                    timeout=timeout, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            raise ClaudeCliError(f"claude CLI timed out after {timeout}s")
        except FileNotFoundError as e:
            raise ClaudeCliError(f"claude CLI not executable: {e}")

        if result.returncode != 0:
            raise ClaudeCliError(
                f"claude exited {result.returncode}: {result.stderr[:800]}")

        content = (result.stdout or "").strip()
        if not content:
            raise ClaudeCliError("claude returned empty stdout")
        return {"content": content, "usage": {}}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: call_claude_cli.py 'your prompt here'", file=sys.stderr)
        sys.exit(2)
    res = call_cli(system="You are a helpful assistant.", user=sys.argv[1])
    print(res["content"])
