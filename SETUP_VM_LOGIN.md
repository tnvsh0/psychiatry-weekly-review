# VM Login Setup — One-Time Procedure

## Why this exists

Earlier attempts ran NotebookLM auth from the user's home PC, then uploaded
cookies to a cloud VM. Google detected the IP mismatch and invalidated the
session within 1–2 days. Every cloud-based attempt (GitHub Actions, Cloud Run,
ephemeral VMs) failed for the same reason.

The fix: log in **from inside the VM**, so the cookies are tied to the VM's
static IP from the start. The VM stays on 24/7, so the IP never changes.

## Architecture

```
weekly-review-vm (me-west1-b)        Static IP: 34.165.125.35
├── Always on (24/7, ~$16/mo)
├── ~/.notebooklm/storage_state.json   ← created via Chrome Remote Desktop
├── cron: keepalive every 6h           ← pings from same IP
└── cron: weekly review Sunday 06:00   ← uses same IP
```

## One-time setup (after vm/install.sh has run on the VM)

### 1. Set up Chrome Remote Desktop access

From the VM (via `gcloud compute ssh`):

```bash
# Make sure CRD is installed (install.sh handles this; if not):
sudo apt-get install -y wget
wget https://dl.google.com/linux/direct/chrome-remote-desktop_current_amd64.deb
sudo apt-get install -y ./chrome-remote-desktop_current_amd64.deb
```

### 2. Pair the VM with your Google account

1. On your home PC, open https://remotedesktop.google.com/headless
2. Click **Set up another computer** → **Begin** → **Next** → **Authorize**
3. Copy the **Debian Linux** command shown
4. Paste and run that command on the VM (via `gcloud compute ssh`)
5. When prompted, set a 6-digit PIN

### 3. Connect and log in to NotebookLM

1. Open https://remotedesktop.google.com/access on your home PC
2. Click on `weekly-review-vm` → enter your PIN
3. **Inside the remote desktop**, open a terminal
4. Run:
   ```bash
   notebooklm login
   ```
5. A Chrome window opens **on the VM** — complete Google sign-in there
6. Press ENTER in the terminal when done

### 4. Verify

Still inside the remote desktop terminal:

```bash
notebooklm list --json
```

Should return your notebooks. You can disconnect from Chrome Remote Desktop now.

## When the session eventually expires

This will happen rarely (weeks → months). When it does, ntfy will notify you.

To refresh:
1. Connect via Chrome Remote Desktop
2. Run `notebooklm login` inside the VM
3. Done

**Never run `notebooklm login` on your home PC and upload to Secret Manager.**
That's the old broken flow.

## Daily/weekly automation (handled by VM cron)

| When             | What                          |
|------------------|-------------------------------|
| Every 6 hours    | `notebooklm list` ping        |
| Sunday 06:00 UTC | Full weekly review + podcasts |

## Cost

- e2-small VM running 24/7 in me-west1: ~$13/mo
- Static external IP (already in use): ~$3/mo
- **Total: ~$16/mo (~₪60)**
