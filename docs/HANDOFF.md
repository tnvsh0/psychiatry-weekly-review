# Handoff — state of the system, 2026-08-03

Written at the end of a long session so the next one can start cold. Covers the
weekly-review project and everything it shares with the two sibling projects on
the same VM.

---

## 1. The shared VM — read this first

`weekly-review-vm` · zone `me-west1-b` · GCP project `psych-research-agent`
· reserved static IP `34.165.125.35` (**never release it** — the stable IP is
what keeps the NotebookLM session valid, not uptime).

**Three projects share this VM, one NotebookLM login (toviagpt@gmail.com):**

| Project | Path on VM | venv | Runs |
|---|---|---|---|
| psychiatry-weekly-review | `/opt/psychiatry-weekly-review` | `/opt/venv` | Sun (reviews), Wed (spotlights) |
| psychiatry-book-podcasts | `/opt/psychiatry-book-podcasts` | `/opt/venv-books` | Mon/Tue/Thu/Fri + Sat night |
| psychiatry-board-study | `/opt/psychiatry-board-study` | `/opt/venv` ⚠️ | daily 06:00 |

⚠️ board-study shares `/opt/venv` with weekly-review. Both venvs are now on
**notebooklm-py 0.7.3**. Board-study was on 0.3.4 semantics until 2026-08-02 —
its `note get` output format has **not** been re-verified after the upgrade
(the board-study session was asked to check; see §6).

### THE rule that caused weeks of failures

```bash
export NOTEBOOKLM_HOME=/home/User/.notebooklm     # ✅ always the ROOT
# ❌ never  /home/User/.notebooklm/profiles/default
```

notebooklm-py ≥ 0.7 appends `profiles/<name>` itself. `run_keepalive.sh` used
to set the home to the profile directory, so every 6 hours it refreshed the
session into `~/.notebooklm/profiles/default/profiles/default/storage_state.json`
while everything else read the real path, which went stale and then "expired".
**The session was never actually expiring.** Fixed in all three runner scripts
(2026-08-03, PR #42) and verified: a manual keepalive now refreshes in place.

In 0.3.x the old value was *correct*, which is why this worked for weeks and
then broke the moment one venv was upgraded.

### Session recovery (no re-login needed in most cases)

```bash
gcloud secrets versions access latest --secret=notebooklm-auth --project=psych-research-agent \
  | sudo -u User tee /home/User/.notebooklm/profiles/default/storage_state.json >/dev/null
sudo chmod 600 /home/User/.notebooklm/profiles/default/storage_state.json
```
A fresh `notebooklm login` **invalidates the previous session** and therefore
breaks the other two projects — always coordinate before doing it. Login must
happen *inside* the VM via Chrome Remote Desktop (never from the home PC).

### Scheduling (Cloud Scheduler, `us-central1`, 8 jobs, all ENABLED)

Every start has a matching stop; the VM is **off most of the day**:

| Day | start | stop |
|---|---|---|
| Sun | 05:50 (reviews) | 12:00 |
| Mon/Tue/Thu/Fri | 04:50 (books) | 12:00 |
| Wed | 05:50 (spotlights + backfill) | 14:00 |
| Sat | 18:50 (books) | 23:00 |

If the VM is found running when it shouldn't be, check for **paused stop jobs**
(all four were paused once, costing ~$16/mo instead of ~$1-3).

⚠️ `/opt/run_review.sh` and `/opt/run_keepalive.sh` are **copies** — `git pull`
does not update them. After changing `vm/*.sh`, run
`sudo cp vm/run_review.sh /opt/run_review.sh` on the VM.

---

## 2. The weekly-review pipeline

`scripts/weekly_review.py --mode reviews|spotlights|all`

**Sunday (reviews):** search ~10 PubMed clusters → split crowded ones
(`SPLIT_THRESHOLD=11`, `SPLIT_TARGET=9` → ~14-17 episodes) → notebooks →
generate → download → **QC** → auto-retry failures → upload (holding flagged
ones as drafts) → digests → RSS → ntfy. Also *selects* next Wednesday's
spotlights and saves `summaries/<date>/spotlight-selection.json`.

**Wednesday (spotlights):** generate exactly the papers Sunday selected (perfect
sync, cross-referenced in both directions) → then a **backfill sweep** that
re-produces any episode from recent weeks whose generation had failed → then
the **QC-trends** agent.

**Channels:** 3 review feeds (child / psychiatry / therapy) + spotlight feed(s),
built by `generate_rss.py`, served from GitHub Pages, MP3s on GitHub Releases.

### Key knobs
- `SPLIT_THRESHOLD` / `SPLIT_TARGET` — episode density. 9/7 was too aggressive
  (19-21 generations → rate-limit losses); 11/9 is the tuned value.
- `MAX_SPOTLIGHT_PER_CHANNEL=3`, `SPOTLIGHT_MIN_SCORE=4`.
- `QC_HOLD_ACCURACY_AT_OR_BELOW=2`, `QC_HOLD_HIGH_SEVERITY_AT_OR_ABOVE=2`.
- `MAX_QC_RETRIES=1`, `MAX_AUTO_RETRY_EPISODES=3` (retries count against the
  same per-run generation budget).

---

## 3. Quality control

`scripts/qc_review.py` — Gemini **listens to the MP3 directly** (multimodal;
no transcription step) and scores accuracy / coverage / fluency 1-5, returning
`discrepancies` [{said, source, severity}], `lost_content`, `missed_papers`.
Writes `summaries/<date>/qc-report.md` + `qc-results.json`, pushes an ntfy with
a link to the report.

**The gate:** episodes with verdict `problem`, accuracy ≤ 2, ≥ 2 high-severity
discrepancies, or real `lost_content` are uploaded as GitHub **draft** releases
— `generate_rss.py` skips drafts, so they never reach Spotify. Clean episodes
publish automatically. Auto-retry regenerates a failing episode once first;
only a second failure reaches the human.

**The judge knows the podcast spec** (`PODCAST_SPEC`) so it does not flag
intended design — the AI disclaimer, full journal names, the opening framing,
analogies, marked consensus-level elaboration. A deterministic filter
(`_clean_discrepancies`) drops rows that merely confirm the audio or repeat the
same name on both sides; anything ambiguous is kept.

**Human tools** (run on the VM):
```bash
python scripts/publish_episode.py    --date <d> --topic <t>   # or --all-held
python scripts/regenerate_episode.py --date <d> --topic <t> [--publish]
python scripts/backfill_episodes.py  --date <d> [--topic <t>] [--dry-run]
python scripts/backfill_episodes.py  --recent 6 --limit 10     # sweep
python scripts/qc_trends.py --weeks 8 --min-count 3
```
`regenerate --publish` publishes **only if the new take passes QC**. Both
regenerate and backfill rebuild the prompt from the *current* topic definitions,
so a redone episode gets every prompt fix since.

**Auditing for lost episodes:** compare topic_ids in
`summaries/<date>/articles.json` against `gh release list` tags for that date.

---

## 4. The prompt (`TONE_GUIDANCE` in weekly_review.py)

Tuned repeatedly from QC findings:
- Airtime split ~20% question+design / **~45% results** / ~35% meaning;
  "methodology is the SETUP, not the destination".
- Going beyond the source is **allowed** when (a) mainstream consensus and
  (b) briefly marked ("זה לא מהמאמר עצמו, אבל ידוע ש...").
- **Analogies encouraged** — but may never smuggle in a mechanism or number.
- Statistics reported as stated: an AUC of 0.70 is *not* "a 70% chance".
- Hosts say 'החוקרים' / 'צוות המחקר' instead of foreign surnames (Hebrew TTS
  garbles them).
- Disclaimer ends **"מול המקור"** — not "המקור המקורי", not "המאמר" (sources
  include books). Say it verbatim.
- Each episode announces the date range it covers.

`scripts/qc_trends.py` aggregates QC findings across weeks into recurring
patterns and **proposes** prompt edits — it never applies them (NotebookLM
can't learn between episodes and is non-deterministic, so autonomous tuning
would chase noise).

---

## 5. Current state (2026-08-03 evening)

- Auth **valid**, VM **off**, all 8 scheduler jobs enabled.
- 2026-08-02 reviews: 17 generated, **16 published**, 0 drafts. Quality notably
  up: 14 episodes at 5/5/5 (historical mean accuracy was 4.33).
  `child_adolescent_misc` was abandoned after 3 attempts — it hallucinated an
  entire study with fabricated statistics; the gate caught it every time.
- Books: **51 episodes, no gaps**, none held. Monday's run failed on the session
  bug and was re-run manually the same day.
- Everything merged to `main` (latest PR #42).

---

## 6. Open items

1. **board-study × notebooklm-py 0.7.3** — `note get` output format not
   re-verified after the shared-venv upgrade; `parse_note.py` could break
   silently. The board-study session ("Sketch-style medical images improvement")
   was messaged with exact test steps. If it broke: **do not downgrade
   `/opt/venv`** (that would break reviews + books) — give board-study its own
   `/opt/venv-study`.
2. **Books QC sends no ntfy.** The books project *does* run QC and writes
   `reports/<date>/qc-report.md` + `qc-results.json` in its own repo, but the
   user never receives a notification. Small fix, worth doing.
3. **Consider separating venvs per project** with pinned versions. The whole
   version-drift incident came from three projects sharing one venv and one
   auth directory.
4. **GitHub Pages builds occasionally stick** in "building", serving a stale
   feed. Fix: `gh api -X POST repos/tnvsh0/psychiatry-weekly-review/pages/builds`
   then poll `.../pages/builds/latest`. A post-run check would automate this.
5. Deferred by the user: expanding to more medical disciplines; a guest
   third voice (impossible — NotebookLM deep-dive is a fixed two-host format).

---

## 7. Facts worth not re-learning

- NotebookLM episode length is capped: `--length` accepts only
  short/default/long, already at `long` (~25 min). Asking the hosts to "be
  longer" does nothing — the only lever on density is fewer articles per part.
- Gemini 2.5 counts "thinking" tokens toward `max_output_tokens`; budget for
  both or replies get cut off mid-JSON.
- One Gemini key (`gemini-api-key`) powers digests, QC and trends. Without it
  those steps skip themselves and podcasts still run.
- Spotlight episodes and backfilled episodes both go through QC; the sweep runs
  after the main QC phase, so backfill does its own judging.

---

## 8. Added 2026-08-20 — disk leak, and what the audio files really are

**The pipeline used to leak disk.** Episodes were downloaded to
`podcasts/<date>/` and never removed, so the shared VM reached 96% full (~7 GB
of ours). The durable copies already live in the GitHub Releases and the Drive
backup — only the run in flight needs local audio. Fixed: `weekly_review` now
deletes each MP3 at the end of the run (after the Drive backup and the feed
build, both of which still need the files), and `scripts/prune_local_audio.py`
reclaims a backlog (`--dry-run`, `--keep-days`). One-time prune freed 6.89 GB;
disk went 96% → 58%. Found by the board-study session, which hit the same
pattern in its own project.

**The "MP3" files are not MP3s.** NotebookLM returns fragmented MPEG-4 audio:

```
$ file podcasts/<date>/<topic>.mp3
ISO Media, MPEG v4 system, Dynamic Adaptive Streaming over HTTP
```

We name them `.mp3` and the RSS enclosure declares `type="audio/mpeg"`. Players
(Spotify included) have accepted this for months, so it is not breaking
playback — but it means `mutagen.mp3.MP3()` fails with "can't sync to MPEG
frame", and the generic `mutagen.File()` reports `length = 0` because a
fragmented MP4 carries no duration in its header. **Consequence:
`<itunes:duration>` has essentially never been emitted** (3 tags across ~60
episodes in feed-child). Getting real durations would need `ffprobe` (ffmpeg is
not installed) or reading the length from NotebookLM's own metadata. This is an
improvement, not a fault — recorded here so nobody re-diagnoses it.

The duration-preservation machinery added with the cleanup (durations.json +
a fallback in `generate_rss`) is correct and harmless, but it only starts
paying off once duration extraction itself works.

**Verified after pruning:** feeds rebuild cleanly (243 releases → 60/77/61/34
episodes) and the only diff versus the committed feeds was `lastBuildDate` —
duration tag count unchanged, nothing lost.

**`.git` is ~820 MB and it IS audio — corrected 2026-08-20.** An earlier note
here claimed no MP3 was ever committed; that was wrong (the local check's
`cat-file` pipeline failed silently on Windows and returned an empty result,
which I read as "none"). Episodes WERE committed back in May 2026, before
`podcasts/` was gitignored:

    podcasts/2026-05-25/psychotherapy.mp3       55 MB
    podcasts/2026-05-10/child_development.mp3   48 MB
    podcasts/2026-05-10/neuroscience.mp3        47 MB

They are reachable from real commits, so `git gc` cannot drop them — it just
packs them (817 MB pack). Every clone of the repo pays that cost. Removing them
needs a history rewrite (`git filter-repo --path podcasts/ --invert-paths`)
plus a force-push, which rewrites every commit SHA. Not done: it is destructive
and the disk pressure was already solved by deleting the working-tree copies.
Revisit only if clone size becomes a real problem.

Lesson: verify a "nothing found" result actually ran — an empty pipeline output
is not evidence of absence.
