#!/bin/bash
# Weekly psychiatry review — runs on the VM every Sunday 06:00 UTC.
# Triggered by cron. After finishing, saves updated session and shuts VM down.

LOG=/var/log/weekly-review-$(date +%Y-%m-%d).log
exec >> "$LOG" 2>&1
echo "=== Weekly review: $(date) ==="

export PATH=/opt/venv/bin:$PATH
cd /opt/psychiatry-weekly-review
git pull --ff-only origin main

export NOTEBOOKLM_AUTH_JSON=$(gcloud secrets versions access latest --secret=notebooklm-auth --project=psych-research-agent)
export GH_TOKEN=$(gcloud secrets versions access latest --secret=github-token --project=psych-research-agent)
export GH_REPO="tnvsh0/psychiatry-weekly-review"
export NTFY_TOPIC="psychiatry-review-tnvsh"
export UI_URL="https://psychiatry-ui-690391711540.us-central1.run.app"

# Refresh NotebookLM auth session before running
echo "Refreshing NotebookLM session..."
python3 << 'REFRESH_PYTHON'
import subprocess
import json
import os
from pathlib import Path

# Write auth from env var to file
auth_json = os.environ.get("NOTEBOOKLM_AUTH_JSON", "")
if auth_json:
    storage_path = Path.home() / ".notebooklm" / "storage_state.json"
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_text(auth_json, encoding="utf-8")
    print(f"  Session loaded from Secret Manager")

# Try to verify by running a list command
result = subprocess.run(
    ["notebooklm", "list", "--json"],
    capture_output=True, text=True, timeout=60,
)
if result.returncode == 0:
    print("  ✓ Session is valid")
else:
    output = (result.stdout + result.stderr).lower()
    if any(w in output for w in ["auth", "expired", "redirect"]):
        print("  ⚠ Session is EXPIRED - will attempt to work with stale session")
    else:
        print(f"  ⚠ List command failed: {result.stderr[:200]}")
REFRESH_PYTHON

python scripts/weekly_review.py
EXIT_CODE=$?

# Save updated session cookies back to Secret Manager (keeps session fresh)
AUTH_FILE="$HOME/.notebooklm/storage_state.json"
if [ -f "$AUTH_FILE" ] && [ $EXIT_CODE -eq 0 ]; then
    echo "Saving updated session to Secret Manager..."
    gcloud secrets versions add notebooklm-auth \
        --data-file="$AUTH_FILE" \
        --project=psych-research-agent 2>/dev/null || true
fi

echo "=== Done: $(date) (exit $EXIT_CODE) ==="

# Shut down VM — Cloud Scheduler will start it again next Sunday
echo "Shutting down VM..."
shutdown -h now
