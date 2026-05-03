#!/bin/bash
# One-time fix: install Playwright Chromium browser for the current user.
# Run if 'notebooklm login' fails with "Executable doesn't exist" error.
#
# Usage:
#   gcloud compute scp vm/fix_playwright.sh weekly-review-vm:/tmp/ --zone=me-west1-b
#   gcloud compute ssh weekly-review-vm --zone=me-west1-b --command="bash /tmp/fix_playwright.sh"

set -e
echo "Installing Playwright Chromium for user: $(whoami)"
export PATH=/opt/venv/bin:$PATH
python -m playwright install chromium --with-deps
echo "Done."
