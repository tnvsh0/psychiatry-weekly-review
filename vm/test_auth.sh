#!/bin/bash
# Quick test: verify NotebookLM session is alive from the VM.
export PATH=/opt/venv/bin:$PATH
export NOTEBOOKLM_AUTH_JSON=$(gcloud secrets versions access latest --secret=notebooklm-auth --project=psych-research-agent)
echo "Testing NotebookLM session..."
notebooklm list --json 2>&1 | head -30
echo "Exit code: $?"
