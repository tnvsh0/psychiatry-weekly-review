#!/bin/bash
# One-time VM setup script.
# Run once after creating the VM:
#   gcloud compute scp vm/install.sh weekly-review-vm:/tmp/ --zone=me-west1-b
#   gcloud compute ssh weekly-review-vm --zone=me-west1-b --command="sudo bash /tmp/install.sh"

set -e
echo "=== VM Install: $(date) ==="

# System packages
apt-get update -y
apt-get install -y --no-install-recommends python3 python3-pip python3-venv git curl

# Clone repo
if [ ! -d /opt/psychiatry-weekly-review ]; then
    git clone https://github.com/tnvsh0/psychiatry-weekly-review.git /opt/psychiatry-weekly-review
else
    git -C /opt/psychiatry-weekly-review pull --ff-only
fi

# Python venv + dependencies
python3 -m venv /opt/venv
/opt/venv/bin/pip install -q --upgrade pip
/opt/venv/bin/pip install -q -r /opt/psychiatry-weekly-review/requirements.txt
/opt/venv/bin/pip install -q playwright
/opt/venv/bin/python -m playwright install chromium --with-deps

# Install run scripts
cp /opt/psychiatry-weekly-review/vm/run_review.sh   /opt/run_review.sh
cp /opt/psychiatry-weekly-review/vm/run_keepalive.sh /opt/run_keepalive.sh
chmod +x /opt/run_review.sh /opt/run_keepalive.sh

# Cron jobs
cat > /etc/cron.d/weekly-review << 'CRON'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# Weekly psychiatry review - Sunday 06:00 UTC
0 6 * * 0 root /opt/run_review.sh

# NotebookLM session keepalive - every 2 hours (runs while VM is on)
0 */2 * * * root /opt/run_keepalive.sh
CRON
chmod 644 /etc/cron.d/weekly-review

echo "=== Setup complete ==="
echo "VM is ready. Cloud Scheduler will start it each Sunday at 05:50 UTC."
