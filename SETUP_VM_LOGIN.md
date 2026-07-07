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
├── cron: keepalive every 6h              ← pings from same IP
├── cron: reviews    Sunday 06:00 UTC     ← uses same IP
└── cron: spotlights Wednesday 06:00 UTC  ← uses same IP
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

| When                | What                                        |
|---------------------|---------------------------------------------|
| Every 6 hours       | `notebooklm list` ping                      |
| Sunday 06:00 UTC    | REVIEWS run — weekly cluster podcasts        |
| Wednesday 06:00 UTC | SPOTLIGHTS run — single-paper deep-dives     |

The weekly run is split across two days so each day fires fewer podcast
generations and stays under NotebookLM's rate limits. `run_review.sh reviews`
runs Sunday; `run_review.sh spotlights` runs Wednesday.

## Optional features (weekly digests + QC review)

Two extra, self-contained features are OFF by default and turn on together when
**one** Gemini API key exists as a GCP secret (read by `vm/run_review.sh`).
Gemini is multimodal, so the same key powers both the text digests and the QC
step, which hands the episode audio straight to Gemini — no separate
speech-to-text service or ffmpeg needed.

| Feature | What it produces |
|---------|------------------|
| **Digests** (items 7+8) | `summaries/<date>/takehome-<channel>.md` (per-channel take-home messages) + `summaries/<date>/clinical-questions.md` (questions to ask patients, grounded in the week's findings) |
| **QC review** | `summaries/<date>/qc-report.md` — Gemini listens to each episode and scores accuracy/coverage/fluency vs the source abstracts; pushes an ntfy summary |

To enable, create the secret in the same GCP project:

```bash
printf '%s' "AI..." | gcloud secrets create gemini-api-key --data-file=- --project=psych-research-agent
```

If the secret is missing, both steps skip themselves — the podcasts still run.
Model is configurable via `DIGEST_MODEL` / `QC_MODEL` env (default
`gemini-2.5-flash`; use `gemini-2.5-pro` for a stricter QC judge). Rough cost
with Flash: a few cents per week.

## Cost

- e2-small VM running 24/7 in me-west1: ~$13/mo
- Static external IP (already in use): ~$3/mo
- **Total: ~$16/mo (~₪60)** (digests + QC add only cents/week on Gemini Flash)
