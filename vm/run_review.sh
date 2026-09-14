#!/bin/bash
# Weekly psychiatry review — runs on the VM via cron. The weekly run is split
# across two days to stay under NotebookLM's generation rate limits:
#   run_review.sh reviews     (Sunday)    — weekly clusters
#   run_review.sh spotlights  (Wednesday) — single-paper deep-dives
#   run_review.sh             (no arg)    — everything in one run (manual)
# VM stays running 24/7 with static IP so the NotebookLM session (created by
# Chrome Remote Desktop login from inside the VM) keeps working from the same
# IP that Google originally validated against.

MODE="${1:-all}"   # reviews | spotlights | all

LOG=/var/log/weekly-review-${MODE}-$(date +%Y-%m-%d).log
exec >> "$LOG" 2>&1
echo "=== Weekly review (mode=$MODE): $(date) ==="

export PATH=/opt/venv/bin:$PATH
# Auth was created by 'User' inside the VM via Chrome Remote Desktop.
# Run the review as User so notebooklm finds the right home directory.
export HOME=/home/User
# NOTEBOOKLM_HOME must be the notebooklm ROOT (not the profile directory):
# notebooklm-py >= 0.7 keeps sessions under <home>/profiles/<name>/ and resolves
# the profile itself. Pointing it at profiles/default made 0.7.x report
# "Authentication expired" against a perfectly good session — which is exactly
# how the 2026-08-01 outage looked. The book-podcasts project sets it the same
# way; both projects share this one login.
export NOTEBOOKLM_HOME=/home/User/.notebooklm
AUTH_FILE=/home/User/.notebooklm/profiles/default/storage_state.json

# Self-heal a mislocated session. If anything ever runs the CLI with
# NOTEBOOKLM_HOME already pointing at the profile directory, 0.7.x appends
# profiles/<name> a second time and the session lands at
# .../profiles/default/profiles/default/storage_state.json — where nothing
# looks for it. That silently broke the 2026-08-02 run ("storage_state.json
# not found") even though a perfectly good session existed. Put it back.
if [ ! -f "$AUTH_FILE" ]; then
    STRAY=$(find /home/User/.notebooklm -name storage_state.json -type f \
            -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
    if [ -n "$STRAY" ]; then
        echo "NOTE: session found at $STRAY — restoring to $AUTH_FILE"
        mkdir -p "$(dirname "$AUTH_FILE")"
        cp "$STRAY" "$AUTH_FILE"
    fi
fi
[ -f "$AUTH_FILE" ] || AUTH_FILE=/home/User/.notebooklm/storage_state.json
cd /opt/psychiatry-weekly-review
# Run git pull as User so any new files stay User-owned (script writes to
# summaries/ and podcasts/ as User; root-owned files would break next run).
sudo -u User git pull --ff-only origin main

# Keep Python dependencies in sync with requirements.txt. Without this, a
# requirement added to the repo (e.g. feedgen for RSS, mutagen for podcast
# duration) silently fails at runtime — the script logs "WARNING: ... failed"
# with empty stderr and continues, producing a broken pipeline.
/opt/venv/bin/pip install -q -r requirements.txt 2>&1 | tail -5


if [ ! -f "$AUTH_FILE" ]; then
    echo "ERROR: $AUTH_FILE not found."
    echo "Connect via Chrome Remote Desktop and run: notebooklm login"
    exit 1
fi

export GH_TOKEN=$(gcloud secrets versions access latest --secret=github-token --project=psych-research-agent)
export GH_REPO="tnvsh0/psychiatry-weekly-review"
export NTFY_TOPIC="psychiatry-review-tnvsh"
export UI_URL="https://psychiatry-ui-690391711540.us-central1.run.app"

# Optional API key — enables the weekly digests (take-home + clinical
# questions) AND the QC review (Gemini listens to each episode and scores it).
# One key does both. If the secret does not exist yet, the var is left empty
# and those steps skip themselves silently.
export GEMINI_API_KEY=$(gcloud secrets versions access latest --secret=gemini-api-key --project=psych-research-agent 2>/dev/null || echo "")

# sudo strips PATH for security even with -E, so we re-set it via env.
# weekly_review.py shells out to `notebooklm` and `gh` — both must be findable.
sudo -u User -E env "PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    /opt/venv/bin/python -u scripts/weekly_review.py --mode "$MODE"
EXIT_CODE=$?

# Back up the (possibly refreshed) session to Secret Manager
if [ -f "$AUTH_FILE" ] && [ $EXIT_CODE -eq 0 ]; then
    echo "Backing up session to Secret Manager..."
    gcloud secrets versions add notebooklm-auth \
        --data-file="$AUTH_FILE" \
        --project=psych-research-agent 2>/dev/null || true
fi

echo "=== Done: $(date) (exit $EXIT_CODE) ==="
# NOTE: This script does not power the VM off, but the VM being on 24/7 is NOT
# what keeps the session valid — the RESERVED static IP is. Cloud Scheduler
# stops/starts this VM around each run and the session survives, because the IP
# is the same on every start. Do not release weekly-review-static-ip.
# (NotebookLM account: toviagpt@gmail.com — shared with the book-podcasts project.)
