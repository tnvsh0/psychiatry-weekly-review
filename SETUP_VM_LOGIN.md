# VM Login Setup — One-Time Procedure

## Why this exists

Earlier attempts ran NotebookLM auth from the user's home PC, then uploaded
cookies to a cloud VM. Google detected the IP mismatch and invalidated the
session within 1–2 days. Every cloud-based attempt (GitHub Actions, Cloud Run,
ephemeral VMs) failed for the same reason.

The fix: log in **from inside the VM**, so the cookies are tied to the VM's
static IP from the start. What keeps the session valid is the **reserved
static IP** (`weekly-review-static-ip`, 34.165.125.35) — it stays attached to
the VM across stop/start, so Google always sees the same IP. The VM does NOT
need to stay on: Cloud Scheduler stops and starts it around each run, and the
session survives because the IP never changes. **Releasing the static IP is
what would break auth — not powering off.**

## Google account

The automation signs in to NotebookLM as **toviagpt@gmail.com** — a dedicated
account, kept separate from personal daily NotebookLM use so the automation's
notebooks never clutter a personal account. Both the weekly-review and the
book-podcasts projects share this one login (`storage_state.json` on the VM).

## Architecture

```
weekly-review-vm (me-west1-b)        Static IP: 34.165.125.35 (reserved)
├── Scheduler-driven start/stop (NOT always-on)   ← IP survives stop/start
├── ~/.notebooklm/storage_state.json   ← toviagpt@gmail.com, via Chrome Remote Desktop
├── cron: keepalive every 6h              ← pings from same IP
├── cron: reviews    Sunday 06:00 UTC     ← uses same IP
├── cron: spotlights Wednesday 06:00 UTC  ← uses same IP
└── cron: book podcasts Fri/Sat           ← separate project, same login
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
5. A Chrome window opens **on the VM** — complete Google sign-in there **with
   toviagpt@gmail.com**. If Chrome is already signed in to another account,
   click "Use another account" and pick toviagpt@gmail.com.
6. Press ENTER in the terminal when done

> Switching accounts later uses this exact same step: run `notebooklm login`
> inside the VM and sign in as the new account. The new `storage_state.json`
> replaces the old one and BOTH projects pick it up immediately. Old notebooks
> left on the previous account won't be auto-deleted (cleanup now runs under the
> new account) — delete them by hand once.

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

### QC publish gate (hold + approve flagged episodes)

When QC is on, each run **QCs episodes BEFORE publishing** and HOLDS only the
genuinely-bad ones (verdict `problem`, or accuracy ≤ 2) as GitHub **draft**
releases. Drafts are excluded from the RSS feeds, so a flagged episode does NOT
reach Spotify until you approve it. Clean episodes publish automatically.

After a run, review `summaries/<date>/qc-report.md`, then on the VM:

```bash
cd /opt/psychiatry-weekly-review
# publish an approved held episode (→ goes live on Spotify):
sudo -u User /opt/venv/bin/python scripts/publish_episode.py --date <date> --topic <topic_id>
# or publish everything that was held:
sudo -u User /opt/venv/bin/python scripts/publish_episode.py --date <date> --all-held
# regenerate a bad episode (NotebookLM is non-deterministic → usually cleaner),
# add --publish to also make it live:
sudo -u User /opt/venv/bin/python scripts/regenerate_episode.py --date <date> --topic <topic_id> [--publish]
```

Held/notebook data lives in `summaries/<date>/run-manifest.json` (notebooks
survive ~4 weeks, so regenerate within that window).

If the secret is missing, QC + gate skip themselves — every episode publishes
automatically as before.
Model is configurable via `DIGEST_MODEL` / `QC_MODEL` env (default
`gemini-2.5-flash`; use `gemini-2.5-pro` for a stricter QC judge). Rough cost
with Flash: a few cents per week.

## Cost

- e2-small VM, scheduler-driven (on only during runs, not 24/7): ~$1–3/mo
- Static external IP (reserved so auth survives — keep it): ~$3/mo
- **Total: ~$5/mo (~₪18)** (digests + QC add only cents/week on Gemini Flash)

> Note: earlier revisions of this doc said the VM must stay on 24/7. That is
> stale. Cloud Scheduler already stops/starts it, and the reserved static IP is
> what preserves the session — see "Why this exists" above.
