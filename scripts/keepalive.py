#!/usr/bin/env python3
"""
Keepalive ping for NotebookLM session.
Runs every 6 hours from Cloud Run to prevent Google from expiring the session.
Just calls 'notebooklm list' and exits.
"""
import os
import sys
import json
import subprocess
from pathlib import Path

# Write auth JSON to disk if provided via env var (same as weekly_review.py)
auth_json = os.environ.get("NOTEBOOKLM_AUTH_JSON", "")
if auth_json:
    storage_path = Path.home() / ".notebooklm" / "storage_state.json"
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_text(auth_json, encoding="utf-8")

print("Pinging NotebookLM to keep session alive...")
result = subprocess.run(
    ["notebooklm", "list", "--json"],
    capture_output=True, text=True
)

output = result.stdout + result.stderr
print(output[:500])

if any(word in output.lower() for word in ["auth", "signin", "login", "expired", "redirect"]):
    print("WARNING: Session appears expired. Run update_auth.ps1 on your PC.")
    sys.exit(1)

print("Session is alive.")
sys.exit(0)
