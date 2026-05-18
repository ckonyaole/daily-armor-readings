# Local Daily Generation Setup

This pipeline now runs in **hybrid mode**: your local Windows machines (Dell + Alienware) generate the daily exegesis using `claude` CLI under your Pro/Max subscription auth (zero API cost). The GitHub Action runs at 09:00 UTC as a safety net — only when neither machine has pushed today's file.

**Cost on a normal day: $0** (subscription is flat-rate; GH Action no-ops).
**Cost on a "both machines off" day: ~$0.25** (GH Action falls back to OpenRouter Opus 4.7).

## One-time setup per machine

### 1. Install Claude Code CLI

```powershell
npm install -g @anthropic-ai/claude-code
claude --version  # verify
```

Then sign in **interactively once** — open a terminal, run `claude`, complete the browser-based subscription login. The auth persists; subsequent headless runs reuse it.

### 2. Clone the repo to a stable path

```powershell
git clone https://github.com/ckonyaole/daily-armor-readings.git C:\Code\daily-armor-readings
```

### 3. Set up the Python venv

```powershell
cd C:\Code\daily-armor-readings
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

This downloads ~2-3 GB (torch + sentence-transformers + deps). Takes 5-10 min.

### 4. Configure git auth

Either SSH key or PAT — `git push` from `C:\Code\daily-armor-readings` should work without prompting. Test:

```powershell
cd C:\Code\daily-armor-readings
git push
```

### 5. Smoke test the generator

```powershell
cd C:\Code\daily-armor-readings
.\scripts\run-daily-cli.ps1 -Force
```

Watch `logs\YYYY-MM-DD.log`. Should:
- Pull repo
- Invoke `claude --print` (counts against subscription window)
- Write `output\YYYY-MM-DD.json`
- Commit + push

If it succeeds, you're done.

### 6. Register the Windows Task Scheduler entry

Option A — via the included XML:

```powershell
schtasks /Create /XML "C:\Code\daily-armor-readings\scripts\daily-armor-task.xml" /TN "DailyArmor"
```

Option B — manually in Task Scheduler GUI:
- **Action:** Start a program
- **Program:** `powershell.exe`
- **Arguments:** `-NoProfile -ExecutionPolicy Bypass -File "C:\Code\daily-armor-readings\scripts\run-daily-cli.ps1"`
- **Trigger:** Daily at 04:00 local time
- **Run whether user is logged on or not:** YES
- **Wake the computer to run this task:** optional (only if you want to wake from sleep)
- **Conditions:** Start the task only if computer is on AC power: NO (so it runs on battery too)

### 7. Verify the scheduled task

```powershell
schtasks /Run /TN "DailyArmor"
# Wait a minute, then check
Get-Content "C:\Code\daily-armor-readings\logs\$(Get-Date -Format yyyy-MM-dd).log" | Select-Object -Last 30
```

## Day-to-day operation

- **Both machines on at 4am:** first one drops `.lock` file, second one sees fresh lock and exits gracefully. Zero duplicate commits.
- **One machine off:** the on one handles it.
- **Both machines off:** GitHub Action runs at 09:00 UTC, generates via OpenRouter Opus 4.7 (~$0.25 cost) as fallback.
- **Both machines off + GH Action also fails:** app falls back to last cached day with "showing yesterday's reading" banner.

## Troubleshooting

| Symptom | Check |
|---|---|
| `.lock` file persists | Auto-clears after 30 min. If stuck, `del C:\Code\daily-armor-readings\.lock` |
| `claude` not found | `npm install -g @anthropic-ai/claude-code` then restart terminal |
| "Not signed in" | Run `claude` interactively, sign in, retry |
| `git push` fails | SSH key/PAT missing — test push manually |
| Python venv missing | Re-run setup step 3 |
| Subscription rate-limit hit | Pro is 5-hour rolling, Max is weekly; one daily run is tiny but if you use Claude Code heavily elsewhere, monitor |
| Today's file wrong / readings off | Override missing — see `scripts/us_feast_overrides.json` for transferred-feast handling |

## Why hybrid vs pure-local

Pure local saves the $7.50/month entirely but loses a day's reading if both machines are off. Hybrid keeps the cost at ~$0/normal day, ~$0.25 occasional fallback day. For a daily devotional app where missing a day matters more than $0.25, hybrid wins.

## Future: iteration 2 (skills)

The current iteration generates base exegesis via Claude CLI. **Iteration 2** will additionally invoke 4 user-installed skills on local runs:
- `bible-entry-icb` — 10 scene-entry questions on today's Gospel
- `step-2-reading-bible` — Ignatian sense-by-sense immersion
- `rosary-mysteries-guide` — today's mystery set + spiritual fruit + verses
- `with-him` — companionship-mode closing reflection

These will add optional sections to the JSON (`bibleEntry`, `gospelImmersion`, `rosaryTieIn`, `walkWithHim`) that the app renders conditionally. CI fallback days won't have them (skills aren't available in GitHub Actions), so the app must tolerate missing fields — which it already does via the schemaVersion 2 forward-compatible parser.
