#!/bin/bash
# Manual auth refresh: Run this whenever auth expires
# Usage: ./vm/update_auth.sh
#
# On local machine:
#   1. notebooklm login
#   2. ./vm/update_auth.sh
#
# This uploads the fresh session to Google Cloud Secret Manager for the VM

echo "=== Uploading NotebookLM session to Secret Manager ==="

AUTH_FILE="$HOME/.notebooklm/storage_state.json"
if [ ! -f "$AUTH_FILE" ]; then
    echo "ERROR: $AUTH_FILE not found"
    echo "Please run 'notebooklm login' first"
    exit 1
fi

echo "Uploading to Google Cloud Secret Manager..."
gcloud secrets versions add notebooklm-auth \
    --data-file="$AUTH_FILE" \
    --project=psych-research-agent

if [ $? -eq 0 ]; then
    echo ""
    echo "SUCCESS! Auth has been updated in Secret Manager."
    echo ""
    echo "The VM will use this fresh session on the next run."
    echo "You can verify with: ./vm/test_auth.sh"
else
    echo "ERROR: Failed to upload auth"
    exit 1
fi
