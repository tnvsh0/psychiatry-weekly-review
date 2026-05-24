#!/bin/bash
# One-time VM setup script. Run as root on the VM.
#
# Architecture: VM runs 24/7 with static IP. User logs in to NotebookLM
# from INSIDE the VM (via Chrome Remote Desktop) so cookies are tied to
# the VM's IP. Cron runs keepalive every 6h + weekly review on Sunday.

set -e
echo "=== VM Install: $(date) ==="

# System packages
apt-get update -y
apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv git curl wget \
    xfce4 xfce4-goodies dbus-x11 \
    fonts-liberation libxss1 libappindicator3-1

# Chrome (needed for both Playwright and the manual login flow)
if ! command -v google-chrome >/dev/null 2>&1; then
    wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -O /tmp/chrome.deb
    apt-get install -y /tmp/chrome.deb
    rm /tmp/chrome.deb
fi

# GitHub CLI (used by weekly_review.py to upload podcasts to GitHub Releases)
if ! command -v gh >/dev/null 2>&1; then
    wget -q https://github.com/cli/cli/releases/download/v2.62.0/gh_2.62.0_linux_amd64.deb -O /tmp/gh.deb
    apt-get install -y /tmp/gh.deb
    rm /tmp/gh.deb
fi

# Chrome Remote Desktop (for one-time NotebookLM login from inside the VM)
if ! command -v chrome-remote-desktop >/dev/null 2>&1; then
    wget -q https://dl.google.com/linux/direct/chrome-remote-desktop_current_amd64.deb -O /tmp/crd.deb
    apt-get install -y /tmp/crd.deb
    rm /tmp/crd.deb
fi

# Tell Chrome Remote Desktop to use Xfce
echo "exec /etc/X11/Xsession /usr/bin/xfce4-session" > /etc/chrome-remote-desktop-session
chmod +x /etc/chrome-remote-desktop-session

# Clone repo (owned by User so runtime can write to summaries/, podcasts/, .git)
if [ ! -d /opt/psychiatry-weekly-review ]; then
    git clone https://github.com/tnvsh0/psychiatry-weekly-review.git /opt/psychiatry-weekly-review
else
    git -C /opt/psychiatry-weekly-review pull --ff-only
fi
chown -R User:User /opt/psychiatry-weekly-review

# Python venv + dependencies
python3 -m venv /opt/venv
/opt/venv/bin/pip install -q --upgrade pip
/opt/venv/bin/pip install -q -r /opt/psychiatry-weekly-review/requirements.txt
/opt/venv/bin/pip install -q playwright
/opt/venv/bin/python -m playwright install chromium --with-deps

# Install run scripts
cp /opt/psychiatry-weekly-review/vm/run_review.sh    /opt/run_review.sh
cp /opt/psychiatry-weekly-review/vm/run_keepalive.sh /opt/run_keepalive.sh
chmod +x /opt/run_review.sh /opt/run_keepalive.sh

# Cron jobs
cat > /etc/cron.d/weekly-review << 'CRON'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# Keepalive every 6 hours — pings NotebookLM from VM's static IP
0 */6 * * * root /opt/run_keepalive.sh

# Weekly psychiatry review — Sunday 06:00 UTC
0 6 * * 0 root /opt/run_review.sh
CRON
chmod 644 /etc/cron.d/weekly-review

echo "=== Setup complete ==="
echo ""
echo "NEXT STEPS (one-time):"
echo "  1. On https://remotedesktop.google.com/headless"
echo "     -> 'Set up another computer' -> 'Begin'"
echo "     Copy the Debian Linux command and run it on this VM as your user."
echo "  2. Connect via https://remotedesktop.google.com/access"
echo "  3. Open a terminal in the remote desktop and run:"
echo "         notebooklm login"
echo "     Complete the Google login in the Chrome window that opens."
echo "  4. Verify with: notebooklm list --json"
echo ""
echo "VM stays on 24/7. Static IP keeps the session valid."
