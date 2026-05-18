# ============================================================
# Daily Armor Readings - local Claude CLI runner
# Runs once per day on each of your Windows machines (Dell + Alienware).
# Generates today's exegesis using `claude` CLI (subscription auth,
# no API cost), commits + pushes to GitHub. Safe to run on both
# machines simultaneously (lock file + git-pull guards).
# ============================================================

param(
    [string]$RepoPath = "C:\Code\daily-armor-readings",
    [string]$PythonPath = "$RepoPath\.venv\Scripts\python.exe",
    [switch]$Force,  # regenerate even if today's file exists
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"
$today = Get-Date -Format "yyyy-MM-dd"
$todayHuman = Get-Date -Format "dddd, MMMM d, yyyy"
$outFile = Join-Path $RepoPath "output\$today.json"
$logFile = Join-Path $RepoPath "logs\$today.log"
$lockFile = Join-Path $RepoPath ".lock"

New-Item -ItemType Directory -Force -Path (Split-Path $logFile) | Out-Null

function Write-Log {
    param([string]$msg)
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

# ----- Lock: prevents both machines from generating simultaneously -----
if (Test-Path $lockFile) {
    $lockAge = (Get-Date) - (Get-Item $lockFile).LastWriteTime
    if ($lockAge.TotalMinutes -lt 30) {
        Write-Log "Lock file is fresh ($([int]$lockAge.TotalMinutes) min old) on another machine. Exiting."
        exit 0
    }
    Write-Log "Stale lock (>30 min old). Removing."
    Remove-Item $lockFile
}

# ----- Pull latest first; other machine may have already pushed today's reading -----
Push-Location $RepoPath
try {
    Write-Log "Pulling latest from origin/main..."
    git pull --rebase --autostash 2>&1 | ForEach-Object { Write-Log $_ }
} catch {
    Write-Log "git pull failed: $_"
}
Pop-Location

if ((Test-Path $outFile) -and -not $Force) {
    Write-Log "output/$today.json already exists. Use -Force to regenerate."
    exit 0
}

# Drop lock
"$env:COMPUTERNAME $(Get-Date -Format o)" | Out-File $lockFile -Encoding utf8

try {
    Write-Log "Generating reading for $todayHuman on $env:COMPUTERNAME"

    if (-not (Test-Path $PythonPath)) {
        throw "Python venv not found at $PythonPath. Run setup: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
    }

    # Verify claude CLI is on PATH
    $claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
    if (-not $claudeCmd) {
        throw "`claude` CLI not on PATH. Install with: npm install -g @anthropic-ai/claude-code (then run `claude` once interactively to sign in)."
    }

    Push-Location $RepoPath
    try {
        Write-Log "Invoking generate.py with --use-claude-cli..."
        $args = @("-m", "scripts.generate", "--date", $today, "--use-claude-cli")
        # PS 5.1 treats native-command stderr as ErrorRecords under
        # ErrorActionPreference=Stop. Wrap in a temporary "Continue" so
        # Python's informational stderr (e.g. "delegating to Claude
        # WebFetch...") doesn't kill the pipeline.
        $prevPref = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $pyOutput = & $PythonPath @args 2>&1
            $exitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $prevPref
        }
        foreach ($line in $pyOutput) {
            Write-Log ([string]$line)
        }
    } finally {
        Pop-Location
    }

    if ($exitCode -ne 0) {
        throw "generate.py exited with code $exitCode"
    }
    if (-not (Test-Path $outFile)) {
        throw "Output file was not created at $outFile"
    }

    Write-Log "Generated: $outFile ($((Get-Item $outFile).Length) bytes)"

    # ----- Commit + push -----
    Push-Location $RepoPath
    try {
        # One more pull before push in case other machine just finished
        git pull --rebase --autostash 2>&1 | Out-Null
        if (-not (Test-Path $outFile)) {
            Write-Log "Other machine produced today's reading during our run. Standing down."
            exit 0
        }
        git add "output/$today.json"
        $changes = git status --porcelain
        if (-not $changes) {
            Write-Log "No changes to commit (other machine pushed identical content)."
        } else {
            git commit -m "daily: $today [$env:COMPUTERNAME via claude CLI]" 2>&1 | ForEach-Object { Write-Log $_ }
            git push origin main 2>&1 | ForEach-Object { Write-Log $_ }
            Write-Log "Pushed to GitHub."
        }
    } finally {
        Pop-Location
    }
} catch {
    Write-Log "ERROR: $_"
    Write-Log $_.ScriptStackTrace
    exit 1
} finally {
    Remove-Item $lockFile -ErrorAction SilentlyContinue
}

Write-Log "Done."
