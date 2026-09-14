#!/usr/bin/env bash
# The single entry point for every scheduled pipeline on this VM.
#
# WHY THIS EXISTS
# ---------------
# The jobs used to be plain cron entries at fixed hours (books at 05:00,
# reviews at 06:00 Sunday, and so on), started by a Cloud Scheduler job that
# boots the VM ten minutes earlier. That has a hole with no error in it
# anywhere:
#
#   * Scheduler POSTs to the Compute API `instances/.../start` endpoint. The
#     API answers 200 OK immediately and does the work asynchronously, so a
#     start that later fails with ZONE_RESOURCE_POOL_EXHAUSTED still looks
#     like a successful job. Retries do not help — there is nothing for
#     Scheduler to retry.
#   * And even when a retry does bring the VM up, a boot at 05:30 has already
#     missed the 05:00 cron slot. The machine sits there, idle and billed,
#     until the stop job turns it off.
#
# That is exactly what happened on 2026-09-10: start failed at 04:50:23, no
# episodes were produced, and no notification was sent, because from every
# component's point of view nothing had gone wrong.
#
# So the trigger moves off the clock and onto the boot. Whenever this VM comes
# up, it works out what it owes for today and runs it. A late start still
# produces episodes.
#
# Cron still calls this too, for the case where the VM is already running at
# the scheduled hour. Running it twice is safe: a lock stops concurrent
# copies, and each job is skipped if today's log already exists.
set -uo pipefail

LOCK=/var/run/dispatch_runs.lock
NTFY_TOPIC="${NTFY_TOPIC:-psychiatry-review-tnvsh}"
LOOK_BACK_DAYS=8

exec 9>"$LOCK" || exit 0
flock -n 9 || { echo "dispatch: another copy holds the lock; nothing to do"; exit 0; }

notify() {                                   # title, body, priority
    curl -fsS -m 15 \
        -H "Title: $1" -H "Priority: ${3:-default}" \
        -d "$2" "https://ntfy.sh/${NTFY_TOPIC}" >/dev/null 2>&1 \
        || echo "dispatch: ntfy failed (continuing)"
}

# Which pipelines does a given weekday owe? 1=Mon .. 7=Sun, UTC throughout —
# these mirror /etc/cron.d exactly, and must keep mirroring it.
jobs_for_dow() {
    case "$1" in
        1) echo "books review:backfill" ;;    # Mon: books + the backfill sweep
        2) echo "books" ;;
        3) echo "review:spotlights" ;;
        4) echo "books" ;;
        5) echo "books" ;;
        6) echo "books" ;;                    # Sat evening
        7) echo "review:reviews" ;;           # Sun
    esac
}

log_for() {                                   # job, date -> log path
    case "$1" in
        books)             echo "/var/log/book-podcasts-daily-$2.log" ;;
        review:reviews)    echo "/var/log/weekly-review-reviews-$2.log" ;;
        review:spotlights) echo "/var/log/weekly-review-spotlights-$2.log" ;;
        review:backfill)   echo "/var/log/weekly-review-backfill-$2.log" ;;
    esac
}

run_job() {
    case "$1" in
        books)             /opt/psychiatry-book-podcasts/vm/run_books.sh daily ;;
        review:reviews)    /opt/run_review.sh reviews ;;
        review:spotlights) /opt/run_review.sh spotlights ;;
        review:backfill)   /opt/run_review.sh backfill ;;
    esac
}

TODAY=$(date -u +%F)
DOW=$(date -u +%u)

# ── Report anything the last few days silently dropped ──────────────────────
# This is the only place a failed boot is ever noticed. If the VM could not
# start on Tuesday, nobody hears about it until it manages to start again —
# but then they do hear about it, by name and date, instead of wondering why
# the feed went quiet.
missed=""
for back in $(seq 1 "$LOOK_BACK_DAYS"); do
    d=$(date -u -d "$back days ago" +%F) || continue
    for job in $(jobs_for_dow "$(date -u -d "$back days ago" +%u)"); do
        [ -f "$(log_for "$job" "$d")" ] || missed="${missed}\n  • ${d}  ${job}"
    done
done
if [ -n "$missed" ]; then
    echo -e "dispatch: MISSED RUNS in the last ${LOOK_BACK_DAYS} days:$missed"
    notify "פרקים שלא נוצרו" \
           "$(echo -e "ריצות שלא התרחשו:${missed}\n\nכנראה שהמכונה לא הצליחה לעלות.")" \
           high
fi

# ── Today's work ────────────────────────────────────────────────────────────
# With no argument (the boot service) this runs everything today owes. With a
# job name (the cron entries) it runs just that one, so Monday's books run at
# 05:00 and backfill sweep at 09:00 stay independent, exactly as before — a
# books run that hangs must not take the backfill down with it.
todo=$(jobs_for_dow "$DOW")
if [ $# -ge 1 ]; then
    case " $todo " in
        *" $1 "*) todo="$1" ;;
        *) echo "dispatch: $1 is not scheduled for $TODAY (dow $DOW) — skipping"
           exit 0 ;;
    esac
fi
if [ -z "$todo" ]; then
    echo "dispatch: nothing scheduled for $TODAY (dow $DOW)"
    exit 0
fi

for job in $todo; do
    lg=$(log_for "$job" "$TODAY")
    if [ -f "$lg" ]; then
        echo "dispatch: $job already ran today ($lg) — skipping"
        continue
    fi
    echo "dispatch: starting $job for $TODAY"
    run_job "$job"
    echo "dispatch: $job finished with status $?"
done
