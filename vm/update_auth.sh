#!/bin/bash
# DEPRECATED — do not use this in the new architecture.
#
# Old flow (BROKEN):
#   1. notebooklm login on user's PC -> cookies tied to home IP
#   2. ./vm/update_auth.sh -> upload cookies to Secret Manager
#   3. VM pulls cookies from Secret Manager -> uses them from VM IP
#   4. Google sees IP mismatch -> invalidates session within ~2 days
#
# New flow (CORRECT):
#   1. Connect to weekly-review-vm via Chrome Remote Desktop
#      (https://remotedesktop.google.com/access)
#   2. Inside the VM, run: notebooklm login
#   3. Cookies are created from the VM's IP, used from same IP -> stable.
#
# See SETUP_VM_LOGIN.md for the full procedure.

echo "ERROR: This script is deprecated."
echo ""
echo "The auth must be created from inside the VM, not uploaded from your PC."
echo "Connect via Chrome Remote Desktop to weekly-review-vm and run:"
echo "    notebooklm login"
echo ""
echo "See SETUP_VM_LOGIN.md for instructions."
exit 1
