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

---

## 9. Added 2026-08-24 — papers with a title but no content

On 2026-08-23 an episode ran **30 minutes on three papers that had no
abstract** — three sides of one autism-diagnosis correspondence, each a 24-char
stub. NotebookLM filled half an hour from the titles alone. It was pulled and
is now a draft.

**Why the regular search can never recover such a paper.** The PubMed query is
`reldate=8, datetype=edat` — an 8-day rolling window on the *entry* date. When
a title-only record later gains its abstract, `edat` does **not** change: it is
the date PubMed first added the record, not the date it was last updated. So
the paper drops out of the window and never comes back. "It'll turn up in next
week's search" is false, and that is the whole reason an explicit queue exists.

**The queue.** `drop_contentless_articles()` writes every contentless paper to
`summaries/deferred-articles.json` with its **base cluster** (`neuroscience`,
not `neuroscience_part2` — part numbers are per-run and meaningless later).
Every reviews run, `load_ready_deferred()` re-queries each PMID, re-enriches it
through `fetch_article_text()` (**PMC full text first, abstract as fallback** —
open-access full text can land before the abstract, and it is the better source
anyway), and folds anything that now has content back into its own cluster's
episode. `DEFERRED_MAX_AGE_DAYS = 28` gives four weekly attempts, then it stops.

The **article** returns, not the episode — right granularity. Resurrecting the
dead episode would rebuild a thin standalone; rejoining the cluster puts the
paper in that week's proper episode alongside everything else.

A PubMed hiccup (`_esummary` returns nothing) keeps the paper queued rather than
dropping it — a transient failure must not look like a decision.

`MIN_ARTICLES_FOR_EPISODE = 1`: only an episode where **nothing** has content is
skipped. Few articles is not a defect — a single paper with a full text made a
sound 12-minute episode on 2026-08-09.

**Seeded by hand:** the 08-23 run predates this gate, so its 14 contentless
papers (3 highimpact, 5 clinical, 3 bio, 2 neuroscience, 1 child_development)
were written into the queue retroactively. All 14 re-checked clean on 08-24 and
remain queued.

---

## 10. Added 2026-08-24 — four ways an episode goes missing

One question ("what happens to a paper that had no abstract?") uncovered a
chain. All four were **silent**: the run exited 0 and the log looked clean.

**1. Generation had no ceiling.** Runs of 15, 16 and 17 episodes lost nothing;
a run of 22 lost **6 (27%)**, with `--retry 3` and the second-chance pass
already in place. That is a daily ceiling, not a rate that spacing fixes.
`MAX_GENERATIONS_PER_RUN = 16`; the remainder is **deferred**, not dropped, and
finished by `--mode backfill` (Monday 09:00 UTC, cron on the VM). A deferred
episode keeps its notebook, its pushed summary and its manifest row.

**2. The ntfy warning was buried.** It did fire on 08-23 — last line, under 22
topic lines, normal priority. It now opens the message, is in the title with
its count, tagged `warning`, priority 4.

**3. The sweep could never recover a spotlight.** `_base_prompt()` looks the
topic up in `TOPICS`, but spotlight topics are built per-run from that week's
selection and are not there → `None` → skip, silently, every week. It now falls
back to the `full_prompt` the run manifest recorded. **Two 08-19 spotlights had
been failing this way since 08-19.**

**4. Generation and download are different failures.** Those same two episodes
had **rendered fine**; only the download failed, printing `Download failed:`
with an empty stderr. Two finished episodes sat in NotebookLM for five days
while every sweep tried to regenerate them. The sweep now checks for a
completed audio artifact first and downloads it — no rendering, no rate-limit
cost. `download_podcast` now names which of the three ways it failed.

**And: a rejected feed push was reported as success.** `Feeds pushed.` printed
unconditionally with the output discarded. The sweep's push was rejected as
non-fast-forward (main moved while it ran), so six recovered episodes stayed
out of the RSS. Both feed pushes now rebase onto `origin/main`, retry once, and
say so when they still fail.

⚠️ **The VM's clone can diverge from `origin/main`.** Its unpushed feed commit
made every later `git pull --ff-only` in `run_review.sh` abort with *"Not
possible to fast-forward"* — so the VM silently ran **stale code** while
reporting a clean run. If a deployed fix does not seem to take effect, check
`git status -sb` on the VM *before* anything else.

### Result
2026-08-23: 22/22 episodes exist (20 published, 2 held by QC).
2026-08-19: both spotlights recovered from their existing audio, QC 5/5/5.
All feeds live and verified against GitHub Pages.

---

## 11. Added 2026-08-24 (evening) — decisions taken, and the stash that nearly cost two episodes

**Decided by the owner and done:**
- `neuroscience_part2` (08-23) regenerated. It had told listeners EEG records
  "thousands of individual neurons" — that was Neuropixels, from a *different*
  paper in the same episode — and overstated what resting-state gamma predicted.
- The empty `child_adolescent_highimpact` (08-23) release **deleted**. Its three
  papers stay in `deferred-articles.json` and return when PubMed publishes them.
- **The books project got the two fixes this project already had** (books PR #1):
  `--retry 3` on generation (it had none — the exact bug that cost this project
  9 episodes), and a notification that names what never got made. "ספרים: 3
  פרקים חדשים" reads like success when 4 were planned; that is how a missing
  book went unseen.

**Backfill now applies the content gate.** Deleting the empty episode makes its
release *missing*, and producing missing releases is the sweep's entire job — it
would have rebuilt it. The sweep now skips any topic where no article has usable
content.

### ⚠️ The 817 MB stash — check before you clear one

`.git` on the VM was 818 MB while GitHub's was 5 MB. `git gc` could not shrink
it, and no branch or tag reached the blobs. The holder was **`refs/stash`** — an
untracked-files stash from 2026-05-26 (`git stash list` showed nothing, because
expiring the reflog had already emptied the stash log while `refs/stash` still
pointed at the commit).

It held 40 files, and **clearing it blind would have destroyed real content**:
- `summaries/2026-05-02/` — articles.json + 5 episode summaries, **missing from
  the repo entirely**.
- `podcasts/2026-05-02/child_adolescent.mp3` and `2026-05-03/…` — two episodes
  with **no GitHub release at all**. Those two dates had zero releases; the audio
  existed nowhere else.

All rescued first: the summaries are committed, both episodes are **draft**
releases (preserved, deliberately out of the feed — publishing 4-month-old
episodes made under the old prompt is the owner's call). Then the stash was
dropped: **818 MB → 5.2 MB**.

### Queued, not done
1. **Books QC sends no ntfy.** It writes `reports/<date>/qc-report.md` and
   `qc-results.json`, and the owner never sees them.
2. **board-study × notebooklm-py 0.7.3** — `note get` output format still never
   re-verified after the shared-venv upgrade; `parse_note.py` may break silently.

---

## 12. Added 2026-08-24 (late) — the two queued items, closed

### board-study × notebooklm-py 0.7.3 — **not exposed**
The daily job is `daily_notify.py` (cron `0 6 * * *`), and it imports json, os,
sys, datetime, pathlib, requests, re and subprocess — **no notebooklm**. The
shared-venv upgrade could not have broken it. The only thing that reads
`note get` output is `scripts/parse_note.py`, a manual helper with no caller in
the repo. Item closed.

**But board-study has been on Day 1 of 144 since 2026-06-03.**
`schedule/progress.json`: `completed_days: []`, `last_studied: null`,
`last_notified_day: 1`. The "sticky" rule only re-sends while the day is
*unnotified* — once Day 1 was announced it has printed "already notified —
skipping" every morning since and sent **nothing**. A sticky reminder that
reminds once is not sticky. Behaviour is as written; whether that is the wanted
behaviour is the owner's call.

### Books QC visibility + real catch-up (books PRs #2, #3)
- The QC judge had been scoring every episode and writing `reports/<date>/`
  since it was added, and **none of it ever reached the owner** — the
  notification reported only how many were held. It now lists each episode's
  accuracy/coverage/fluency, marks held and regenerated ones, and links the
  report.
- **There was no catch-up, only an accident that usually works.** A failed
  episode does not advance `next_episode`, so the next run retries it — true at
  one episode per run, false for `freud` at six: `next_episode = max(next, n+1)`
  means a failure at 5 followed by successes 6-11 sets it to 12 and **5 is never
  looked at again**. Selection now starts from the first incomplete episode.
  Verified: no book has a gap today; every `completed` list is contiguous.
- `ERROR download:` printed an empty stderr — same bug as this project had.
  Fixed the same way.

### What actually happened on the two silent book days
| day | what | outcome |
|---|---|---|
| Mon 2026-08-17 | **the VM never booted** — `journalctl --list-boots` jumps 08-16 → 08-18; no log from any project | scheduler is ENABLED and has fired every Monday since, incl. 08-24. One-off. |
| Tue 2026-08-18 | ran, session verified, **all 4 downloads failed** with empty stderr | same failure mode as the 08-19 spotlights the next day |

**Nothing was lost.** Every book's `completed` is contiguous 1..N; those
episodes were produced on later run days. The cost was two days of schedule
slip and a run's worth of wasted rendering.

---

## 13. Added 2026-08-24 (night) — QC across 222 episodes, and what it changed

Read every QC report both projects had ever written: 120 weekly-review
episodes over 12 run dates, 102 book episodes over 24 days.

### What the data said — including two of my own hypotheses it killed
- **"NotebookLM fabricates when the material is thin."** Wrong, and backwards:
  the episodes that invented a paper had a median 63,149 chars of source text
  against 14,872 for clean ones.
- **"Full text is riskier than abstracts."** Looks true raw (0.31 vs 0.05
  high-severity per episode) and is a size confound. Per 10k chars: **0.076 vs
  0.069 — the same.** Moving toward full texts costs nothing in accuracy.
- **Density is the real driver**, and it is steep:

  | articles/episode | high-severity per episode |
  |---|---|
  | 1 | **0.00** (n=17) |
  | 2-3 | **0.00** (n=5) |
  | 4-5 | 0.07 (n=29) |
  | 6-7 | 0.16 (n=45) |
  | **8+** | **0.50** (n=24) |

  All 16 single-paper spotlights: zero. The apparent "child channel problem"
  dissolves on inspection — every `child_adolescent_misc` finding came from the
  runs where it was **not** split (10 articles on 08-02, 9 on 08-16).
  `SPLIT_THRESHOLD=8 / SPLIT_TARGET=6` is doing its job: 2026-08-23 was the most
  accurate run ever recorded (mean 4.73, against 4.00 in mid-July). **Not
  lowering it further** — the owner is happy with the episodes and the data
  agrees.

### Prompt: five failures, four of which had no rule (PR #65)
Inventing a paper outright (11 of 21 high-severity findings); carrying a fact
between papers in one episode; collapsing a mixed result; dropping a trial arm;
supplying a number the source states qualitatively. Each rule in `TONE_GUIDANCE`
now names its real failure — an abstract instruction the model already
nominally follows is what let these through.

### The books QC gate had never held anything (books PR #4)
102 episodes, 29 high-severity discrepancies, **zero holds**. `should_hold`
fired only on a `problem` verdict or accuracy ≤ 2; no verdict was `problem` and
no accuracy went below 3. 22 episodes were marked `review` and all 22 published.
Five carried two or more hard errors — **lithium toxicity "above 0.2 or 0.4"
(the book says 1.2 mEq/L)**, risperidone and aripiprazole called off-label for
irritability in ASD (both FDA-approved), a TAT of 20 cards (it is 10), and
invented 4×/7× risk multipliers. All five were regenerated at the owner's
instruction; every one came back with **zero** high-severity findings except
`stahl-004`, which went 4 → 1 (nicotinic desensitisation described as
milliseconds; it is minutes) and published under the threshold.

### "Held" meant "held forever" — in BOTH projects (PR #66, books PR #6)
A held episode got its in-run retries and was then never looked at again. The
weekly-review sweep counted a **draft as "present"** and walked past it: five
episodes had been sitting as drafts since July, out of the feed and unmentioned.
Both projects now give a held episode bounded further attempts on later runs,
still gated, and name it at raised priority only once the automation is spent.
A recovered episode is now cleared from the held list — it wasn't, which would
have retried it forever and kept it out of the feed after it came out right.

⚠️ Not every draft is a QC hold. The 2026-05-02/03 rescues are drafts **on
purpose**; the retry requires a manifest `nb_id`, which protects them.

### Silent failures found by using the fixes, not by reading them
- **The judge was truncated and the episode published unjudged.** `dulcan-007`
  (40 pages) produced a verdict past `max_output_tokens=8192`; `json.loads`
  raised, and a failed judge is indistinguishable from a disabled one, so the
  fail-open path published it. Re-judged with more room: **17 discrepancies, and
  the gate would have held it.** Regenerated → 5/5/5, zero. (books PRs #9, #10 —
  the latter adds `--judge-only`, since re-rendering a good 60 MB episode just
  to obtain a verdict is waste.)
- **My own rebase fallback failed in production**: no git identity on the VM
  clone, leaving a detached HEAD mid-replay — worse than the divergence it was
  meant to repair (books PRs #7, #8).
- **Two regen runs in one day erased each other's reports** (books PR #11).
- **Books never deleted a local MP3**: 4.5 GB across 26 folders. GCS holds the
  durable copy and the manifest holds the duration, so the local file was never
  the only one. Reclaimed and automated; **disk 12 GB → 6.8 GB used**.
