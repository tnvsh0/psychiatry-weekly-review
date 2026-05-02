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
