#!/bin/bash
# Weekly psychiatry review — runs on the VM every Sunday 06:00 UTC.
# Triggered by cron. VM stays running 24/7 with static IP so the NotebookLM
# session (created by Chrome Remote Desktop login from inside the VM) keeps
# working from the same IP that Google originally validated against.

LOG=/var/log/weekly-review-$(date +%Y-%m-%d).log
exec >> "$LOG" 2>&1
echo "=== Weekly review: $(date) ==="

export PATH=/opt/venv/bin:$PATH
# Auth was created by 'User' inside the VM via Chrome Remote Desktop.
# Run the review as User so notebooklm finds the right home directory.
export HOME=/home/User
export NOTEBOOKLM_HOME=/home/User/.notebooklm
cd /opt/psychiatry-weekly-review
# Run git pull as User so any new files stay User-owned (script writes to
# summaries/ and podcasts/ as User; root-owned files would break next run).
sudo -u User git pull --ff-only origin main

# Keep Python dependencies in sync with requirements.txt. Without this, a
# requirement added to the repo (e.g. feedgen for RSS, mutagen for podcast
# duration) silently fails at runtime — the script logs "WARNING: ... failed"
# with empty stderr and continues, producing a broken pipeline.
/opt/venv/bin/pip install -q -r requirements.txt 2>&1 | tail -5

AUTH_FILE="/home/User/.notebooklm/storage_state.json"
if [ ! -f "$AUTH_FILE" ]; then
    echo "ERROR: $AUTH_FILE not found."
    echo "Connect via Chrome Remote Desktop and run: notebooklm login"
    exit 1
fi

export GH_TOKEN=$(gcloud secrets versions access latest --secret=github-token --project=psych-research-agent)
export GH_REPO="tnvsh0/psychiatry-weekly-review"
export NTFY_TOPIC="psychiatry-review-tnvsh"
export UI_URL="https://psychiatry-ui-690391711540.us-central1.run.app"

# sudo strips PATH for security even with -E, so we re-set it via env.
# weekly_review.py shells out to `notebooklm` and `gh` — both must be findable.
sudo -u User -E env "PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    /opt/venv/bin/python -u scripts/weekly_review.py
EXIT_CODE=$?

# Back up the (possibly refreshed) session to Secret Manager
if [ -f "$AUTH_FILE" ] && [ $EXIT_CODE -eq 0 ]; then
    echo "Backing up session to Secret Manager..."
    gcloud secrets versions add notebooklm-auth \
        --data-file="$AUTH_FILE" \
        --project=psych-research-agent 2>/dev/null || true
fi

echo "=== Done: $(date) (exit $EXIT_CODE) ==="
# NOTE: Do NOT shut down the VM. Keeping it on preserves the IP Google
# validated the session against. Static IP + always-on = stable session.
