#!/bin/bash
# Diagnostic test: verify NotebookLM session is alive
# Usage: ./vm/test_auth.sh
#   or on VM: gcloud compute ssh weekly-review-vm --zone=me-west1-b --command='bash /opt/psychiatry-weekly-review/vm/test_auth.sh'

set -e
export PATH=/opt/venv/bin:$PATH

echo "=== NotebookLM Auth Test ==="
echo ""

# Step 1: Fetch auth from Secret Manager
echo "1. Fetching auth from Google Cloud Secret Manager..."
export NOTEBOOKLM_AUTH_JSON=$(gcloud secrets versions access latest --secret=notebooklm-auth --project=psych-research-agent 2>&1)
if [ -z "$NOTEBOOKLM_AUTH_JSON" ]; then
    echo "   ✗ FAILED: Could not fetch auth from Secret Manager"
    echo "   Make sure gcloud is configured and the secret exists"
    exit 1
fi
echo "   ✓ Auth fetched ($(echo "$NOTEBOOKLM_AUTH_JSON" | wc -c) bytes)"
echo ""

# Step 2: Write to storage
echo "2. Writing auth to ~/.notebooklm/storage_state.json..."
mkdir -p ~/.notebooklm
echo "$NOTEBOOKLM_AUTH_JSON" > ~/.notebooklm/storage_state.json
echo "   ✓ Auth written"
echo ""

# Step 3: Test basic status (quick check)
echo "3. Testing 'notebooklm status'..."
if notebooklm status 2>&1 | head -5; then
    echo "   ✓ Status command succeeded"
else
    echo "   ⚠ Status command had issues"
fi
echo ""

# Step 4: Test list command (full auth check)
echo "4. Testing 'notebooklm list --json' (FULL AUTH CHECK)..."
result=$(notebooklm list --json 2>&1)
exit_code=$?

if [ $exit_code -eq 0 ]; then
    nb_count=$(echo "$result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('notebooks', [])))" 2>/dev/null || echo "?")
    echo "   ✓ List succeeded! Found $nb_count notebooks"
    echo ""
    echo "   RESULT: ✅ AUTH IS VALID"
else
    echo "   ✗ List command failed"
    echo ""
    # Check for specific error patterns
    if echo "$result" | grep -qi "auth\|expired\|signin\|redirect"; then
        echo "   RESULT: ❌ AUTH IS EXPIRED OR INVALID"
        echo "   Action required: Run 'notebooklm login' to re-authenticate"
    elif echo "$result" | grep -qi "error"; then
        echo "   RESULT: ⚠ API ERROR"
        echo "$result" | head -5
    else
        echo "   RESULT: ⚠ UNKNOWN ERROR"
        echo "$result" | head -5
    fi
    exit 1
fi
