#!/bin/bash
# NotebookLM session keepalive — runs on the VM every 2 hours while VM is on.
# Saves updated session cookies back to Secret Manager after each successful ping.

exec >> /var/log/keepalive.log 2>&1
echo "--- Keepalive: $(date) ---"

export PATH=/opt/venv/bin:$PATH
cd /opt/psychiatry-weekly-review

export NOTEBOOKLM_AUTH_JSON=$(gcloud secrets versions access latest --secret=notebooklm-auth --project=psych-research-agent)
python scripts/keepalive.py
EXIT_CODE=$?

# Save updated session cookies back to Secret Manager
AUTH_FILE="$HOME/.notebooklm/storage_state.json"
if [ -f "$AUTH_FILE" ] && [ $EXIT_CODE -eq 0 ]; then
    gcloud secrets versions add notebooklm-auth \
        --data-file="$AUTH_FILE" \
        --project=psych-research-agent 2>/dev/null || true
    echo "Session saved to Secret Manager."
fi
