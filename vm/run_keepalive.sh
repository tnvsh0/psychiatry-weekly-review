#!/bin/bash
# NotebookLM session keepalive — runs every 6h while VM is on.
# Pings NotebookLM from the VM's static IP to reset Google's inactivity clock.
# Critical: this MUST run from the same IP the user logged in from (the VM's
# static IP, set up via Chrome Remote Desktop). Running from any other IP
# will cause Google to invalidate the session.

exec >> /var/log/keepalive.log 2>&1
echo "--- Keepalive: $(date) ---"

# Auth was created by 'User' inside the VM via Chrome Remote Desktop.
# Cron runs as root, so we must explicitly target User's home and run
# notebooklm as User (matching HOME for token paths).
export PATH=/opt/venv/bin:$PATH
export HOME=/home/User
# NOTEBOOKLM_HOME must be the notebooklm ROOT, never the profile directory:
# notebooklm-py >= 0.7 appends profiles/<name> itself. Setting it to
# dirname(AUTH_FILE) — i.e. .../profiles/default — made this script refresh the
# session into .../profiles/default/profiles/default/storage_state.json every
# 6 hours, while every other job kept reading the (now stale) real path. That
# is what repeatedly looked like "the session expired" and cost several runs.
export NOTEBOOKLM_HOME=/home/User/.notebooklm
AUTH_FILE=/home/User/.notebooklm/profiles/default/storage_state.json
[ -f "$AUTH_FILE" ] || AUTH_FILE=/home/User/.notebooklm/storage_state.json
cd /opt/psychiatry-weekly-review


if [ ! -f "$AUTH_FILE" ]; then
    echo "WARNING: $AUTH_FILE not found. Run 'notebooklm login' via Chrome Remote Desktop."
    exit 0
fi

# Lightweight ping to keep session warm. Output is checked but exit is always
# 0 — keepalive failure shouldn't crash anything.
output=$(sudo -u User -E /opt/venv/bin/notebooklm list --json 2>&1) || true

if echo "$output" | grep -qi "auth\|signin\|login\|expired\|redirect"; then
    echo "WARNING: session appears expired."
    echo "Connect via Chrome Remote Desktop and run: notebooklm login"
    # Notify user via ntfy if configured
    NTFY_TOPIC="psychiatry-review-tnvsh"
    curl -s -X POST "https://ntfy.sh/${NTFY_TOPIC}" \
        -H "Title: NotebookLM session expired" \
        -H "Priority: high" \
        -d "Connect to weekly-review-vm via Chrome Remote Desktop and run: notebooklm login" \
        > /dev/null 2>&1 || true
    exit 0
fi

echo "Session is alive."

# Save back to Secret Manager (keeps a fresh backup)
gcloud secrets versions add notebooklm-auth \
    --data-file="$AUTH_FILE" \
    --project=psych-research-agent > /dev/null 2>&1 || true
