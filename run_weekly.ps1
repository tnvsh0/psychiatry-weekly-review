# run_weekly.ps1
# Runs the weekly psychiatry literature review on the local machine.
# Called by Windows Task Scheduler every Sunday at 09:00 Israel time.
#
# Requirements (one-time setup via setup_local_task.ps1):
#   - Python 3.10+ installed (python.exe on PATH)
#   - notebooklm login done once  (notebooklm-py package installed)
#   - gh CLI installed and authenticated
#   - This file lives in the repo root

$ErrorActionPreference = "Stop"

# Resolve repo root (same folder as this script)
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# Log file for this run
$LogDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("run_" + (Get-Date -Format "yyyy-MM-dd_HH-mm") + ".log")

function Log($msg) {
    $line = "$(Get-Date -Format 'HH:mm:ss')  $msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Log "===== Weekly Psychiatry Review starting ====="
Log "Repo  : $RepoRoot"
Log "Log   : $LogFile"

# Pull latest code so the script is always up to date
Log "Pulling latest code from GitHub..."
Set-Location $RepoRoot
git pull --ff-only 2>&1 | ForEach-Object { Log $_ }

# Set environment variables
$env:GH_REPO    = "tnvsh0/psychiatry-weekly-review"
$env:NTFY_TOPIC = "psychiatry-review-tnvsh"
$env:UI_URL     = "https://psychiatry-ui-690391711540.us-central1.run.app"

# Get GitHub token from gh CLI (no hardcoding)
try {
    $ghToken = (gh auth token 2>$null).Trim()
    if ($ghToken) {
        $env:GH_TOKEN = $ghToken
        Log "GitHub token: OK"
    } else {
        Log "WARNING: gh CLI not authenticated - podcast uploads may fail"
    }
} catch {
    Log "WARNING: Could not get GitHub token: $_"
}

# NOTEBOOKLM_AUTH_JSON is intentionally NOT set.
# The script detects ~/.notebooklm/storage_state.json automatically.
# That file was created by running: notebooklm login
# It stays valid for weeks when used from the same home IP.

# Install / upgrade Python dependencies
Log "Installing Python dependencies..."
python -m pip install -q --upgrade pip
python -m pip install -q -r "$RepoRoot\requirements.txt"

# Run the review
Log "Starting weekly_review.py..."
$startTime = Get-Date
python "$RepoRoot\scripts\weekly_review.py" 2>&1 | ForEach-Object { Log $_ }
$elapsed = (Get-Date) - $startTime

Log "===== Done in $([int]$elapsed.TotalMinutes) min $($elapsed.Seconds) sec ====="
