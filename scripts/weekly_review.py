#!/usr/bin/env python3
"""
Weekly Psychiatry Literature Review
────────────────────────────────────
1. Search PubMed for real articles from the past 7 days
2. Create a NotebookLM notebook with the articles as sources
3. Generate a clinical briefing document inside the notebook
4. Generate a podcast and WAIT until it is fully ready
5. Download the podcast and upload it to a GitHub Release
6. Send a push notification (ntfy) with direct links to everything

IMPORTANT: Never fabricates articles — only real PubMed data is used.
"""

import os
import sys
import json
import time
import subprocess
import requests
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────────────────
PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
TODAY       = datetime.utcnow()
DATE_STR    = TODAY.strftime("%Y-%m-%d")
WEEK_START  = TODAY - timedelta(days=7)

SEARCHES = [
    ("Child & Adolescent Psychiatry",
     '"child psychiatry"[MeSH] OR "adolescent psychiatry"[MeSH] OR '
     '"autism spectrum disorder"[Title] OR "attention deficit disorder"[MeSH]'),
    ("Child Neurology & Neurodevelopment",
     '"child neurology"[MeSH] OR "neurodevelopmental disorders"[MeSH] OR '
     '"pediatric neurology"[Title/Abstract]'),
    ("Child Development & Mental Health",
     '"child development"[MeSH] AND ("mental health"[Title/Abstract] OR "behavior"[MeSH])'),
    ("Adult Psychiatry — High Impact",
     '("schizophrenia"[MeSH] OR "depressive disorder"[MeSH] OR "bipolar disorder"[MeSH]) AND '
     '("randomized controlled trial"[pt] OR "meta-analysis"[pt] OR "systematic review"[pt])'),
    ("Neuroscience & Cognition",
     '"brain development"[MeSH] OR ("cognitive development"[MeSH] AND "child"[MeSH])'),
    ("Psychotherapy & Interventions",
     '"psychotherapy"[MeSH] AND ("child"[MeSH] OR "adolescent"[MeSH]) AND '
     '("randomized controlled trial"[pt] OR "clinical trial"[pt])'),
    ("Psychopharmacology — Pediatric",
     '("antidepressive agents"[MeSH] OR "antipsychotic agents"[MeSH] OR "stimulants"[MeSH]) AND '
     '("child"[MeSH] OR "adolescent"[MeSH])'),
]

CATEGORY_HEBREW = {
    "Child & Adolescent Psychiatry":     "פסיכיאטריה של הילד והמתבגר",
    "Child Neurology & Neurodevelopment": "נוירולוגיה ונוירו-התפתחות",
    "Child Development & Mental Health":  "התפתחות הילד ובריאות הנפש",
    "Adult Psychiatry — High Impact":     "פסיכיאטריה של המבוגר",
    "Neuroscience & Cognition":           "מדעי המוח וקוגניציה",
    "Psychotherapy & Interventions":      "פסיכותרפיה והתערבויות",
    "Psychopharmacology — Pediatric":     "פסיכופרמקולוגיה ילדית",
}


# ── Step 1: PubMed Search ──────────────────────────────────────────────────────
def search_pubmed():
    print("🔍 Searching PubMed...")
    all_pmids, pmid_to_cat = [], {}

    for label, query in SEARCHES:
        try:
            r = requests.get(PUBMED_BASE + "esearch.fcgi", params={
                "db": "pubmed", "term": query,
                "reldate": 8, "datetype": "edat",
                "retmax": 8, "retmode": "json", "sort": "relevance",
            }, timeout=30)
            r.raise_for_status()
            ids = r.json().get("esearchresult", {}).get("idlist", [])
            for pid in ids:
                if pid not in pmid_to_cat:
                    pmid_to_cat[pid] = label
                    all_pmids.append(pid)
            print(f"  [{label}]: {len(ids)} articles")
            time.sleep(0.5)
        except Exception as e:
            print(f"  ⚠️  Search failed for {label}: {e}")

    if not all_pmids:
        print("❌ No articles found!")
        return []

    articles = []
    try:
        r = requests.get(PUBMED_BASE + "esummary.fcgi", params={
            "db": "pubmed", "id": ",".join(all_pmids[:40]), "retmode": "json",
        }, timeout=30)
        r.raise_for_status()
        result = r.json().get("result", {})

        for pmid in all_pmids[:40]:
            if pmid == "uids":
                continue
            doc = result.get(pmid, {})
            if not doc or doc.get("error"):
                continue
            authors = doc.get("authors", [])
            author_str = authors[0]["name"] if authors else "Unknown"
            if len(authors) > 2:
                author_str += " et al."
            elif len(authors) == 2:
                author_str += f", {authors[-1]['name']}"

            articles.append({
                "pmid":     pmid,
                "title":    doc.get("title", "").rstrip("."),
                "journal":  doc.get("source", ""),
                "authors":  author_str,
                "pub_date": doc.get("pubdate", ""),
                "url":      f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "category": pmid_to_cat.get(pmid, "Other"),
                "abstract": "",
            })
    except Exception as e:
        print(f"❌ Error fetching summaries: {e}")
        return []

    print(f"✅ Found {len(articles)} articles")
    return articles


# ── Step 2: Fetch Abstracts ────────────────────────────────────────────────────
def fetch_abstracts(articles):
    print("📖 Fetching abstracts...")
    for i, article in enumerate(articles):
        try:
            r = requests.get(PUBMED_BASE + "efetch.fcgi", params={
                "db": "pubmed", "id": article["pmid"],
                "rettype": "abstract", "retmode": "text",
            }, timeout=20)
            lines = [l.strip() for l in r.text.strip().split("\n") if l.strip()]
            abstract_lines, in_abstract = [], False
            for line in lines:
                if "Abstract" in line[:30] or line.upper().startswith("ABSTRACT"):
                    in_abstract = True
                    continue
                if in_abstract and any(line.startswith(x) for x in ["PMID:", "DOI:", "Copyright", "©"]):
                    break
                if in_abstract:
                    abstract_lines.append(line)
            article["abstract"] = " ".join(abstract_lines[:8]) or "(Abstract not available)"
            time.sleep(0.3)
        except Exception:
            article["abstract"] = "(Could not fetch abstract)"

        if (i + 1) % 5 == 0:
            print(f"  {i+1}/{len(articles)} done...")

    return articles


# ── Step 3: Create Markdown Summary ───────────────────────────────────────────
def create_summary(articles):
    print("📝 Creating summary document...")
    by_cat = defaultdict(list)
    for a in articles:
        by_cat[a["category"]].append(a)

    date_range = f"{WEEK_START.strftime('%d/%m/%Y')} – {TODAY.strftime('%d/%m/%Y')}"
    lines = [
        "# 📚 סקירת ספרות שבועית — פסיכיאטריה של הילד והמתבגר",
        "",
        f"**תאריך:** {TODAY.strftime('%d/%m/%Y')} | **תקופה מכוסה:** {date_range}",
        f"**מספר מאמרים:** {len(articles)}",
        "",
        "---",
        "",
    ]

    for cat, cat_articles in by_cat.items():
        heb = CATEGORY_HEBREW.get(cat, cat)
        lines += [f"## {heb}", f"*{cat}*", ""]
        for a in cat_articles:
            abstract = a.get("abstract", "")
            if len(abstract) > 500:
                abstract = abstract[:500] + "…"
            lines += [
                f"### {a['title']}",
                f"**כתב עת:** {a['journal']} | **מחברים:** {a['authors']} | **תאריך:** {a['pub_date']}",
                "",
                abstract,
                "",
                f"🔗 [קישור למאמר ב-PubMed]({a['url']})",
                "",
                "---",
                "",
            ]

    lines += [
        "## 📝 הערות",
        "- מאמרים נמצאו אוטומטית דרך PubMed E-utilities API",
        "- הסיכומים מבוססים על תקצירים (Abstracts) בלבד — יש לקרוא את המאמר המלא לפני שימוש קליני",
        "",
        f"*נוצר אוטומטית ב-{TODAY.strftime('%d/%m/%Y %H:%M')} UTC*",
    ]

    out_dir = Path("summaries")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"weekly_review_{DATE_STR}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ Summary saved: {out_path}")
    return str(out_path)


# ── Step 4: NotebookLM — Notebook + Sources + Briefing ────────────────────────
def create_notebook_and_briefing(articles, env):
    """Create notebook, add sources, wait for processing, generate briefing doc.
    Returns (notebook_url, nb_id) or (None, None) on failure."""

    print("🗒️  Creating NotebookLM notebook...")
    try:
        out = subprocess.run(
            ["notebooklm", "create", f"סקירת ספרות שבועית — {DATE_STR}", "--json"],
            capture_output=True, text=True, env=env, timeout=60,
        )
        nb_data = json.loads(out.stdout.strip())
        nb_id   = nb_data["notebook"]["id"]
        nb_url  = f"https://notebooklm.google.com/notebook/{nb_id}"
        print(f"✅ Notebook: {nb_id}")
    except Exception as e:
        print(f"❌ Could not create notebook: {e}")
        return None, None

    subprocess.run(["notebooklm", "use", nb_id], env=env, timeout=30)

    # Add article URLs as sources (max 20)
    print(f"📎 Adding {min(len(articles), 20)} sources...")
    for a in articles[:20]:
        subprocess.run(
            ["notebooklm", "source", "add", a["url"], "--json"],
            capture_output=True, text=True, env=env, timeout=60,
        )
        time.sleep(2)

    # Wait for sources to be indexed
    print("⏳ Waiting for sources to be indexed...")
    for _ in range(10):
        time.sleep(30)
        try:
            out = subprocess.run(
                ["notebooklm", "source", "list", "--json"],
                capture_output=True, text=True, env=env, timeout=30,
            )
            processing = sum(
                1 for s in json.loads(out.stdout).get("sources", [])
                if s.get("status") == "processing"
            )
            print(f"  {processing} sources still processing...")
            if processing == 0:
                break
        except Exception:
            pass

    # Generate briefing document
    print("📄 Generating briefing document...")
    subprocess.run([
        "notebooklm", "generate", "report", "--format", "briefing-doc",
        "--append",
        "This is a weekly literature review for a child and adolescent psychiatry resident. "
        "Focus on clinical relevance, therapeutic implications, and practice-changing findings.",
        "--json",
    ], env=env, timeout=120)

    return nb_url, nb_id


# ── Step 5: Generate Podcast + Wait Until Ready ────────────────────────────────
def generate_and_wait_for_podcast(env, max_wait_seconds=2700):
    """Start podcast generation and block until it is completed.
    max_wait_seconds: 45 minutes default (podcasts usually take 10–30 min).
    Returns artifact_id or None."""

    print("🎙️  Starting podcast generation...")
    artifact_id = None
    try:
        out = subprocess.run([
            "notebooklm", "generate", "audio",
            "Create an engaging, expert-level discussion about this week's most impactful "
            "findings in child and adolescent psychiatry and related fields. "
            "The audience is a psychiatry resident who values both scientific depth "
            "and direct clinical relevance.",
            "--format", "deep-dive", "--json",
        ], capture_output=True, text=True, env=env, timeout=120)
        data = json.loads(out.stdout.strip())
        artifact_id = data.get("task_id", "")
        print(f"  Podcast started — artifact ID: {artifact_id}")
    except Exception as e:
        print(f"❌ Could not start podcast: {e}")
        return None

    if not artifact_id:
        return None

    # Poll until completed
    print(f"⏳ Waiting for podcast (up to {max_wait_seconds // 60} min)...")
    start = time.time()
    poll_interval = 60  # check every 60 seconds

    while time.time() - start < max_wait_seconds:
        time.sleep(poll_interval)
        try:
            out = subprocess.run(
                ["notebooklm", "artifact", "list", "--json"],
                capture_output=True, text=True, env=env, timeout=30,
            )
            artifacts = json.loads(out.stdout).get("artifacts", [])
            for a in artifacts:
                if a.get("id") == artifact_id:
                    status = a.get("status", "unknown")
                    elapsed = int(time.time() - start)
                    print(f"  [{elapsed//60}m] Podcast status: {status}")
                    if status == "completed":
                        print("✅ Podcast ready!")
                        return artifact_id
                    elif status in ("failed", "unknown"):
                        print(f"❌ Podcast failed with status: {status}")
                        return None
        except Exception as e:
            print(f"  Warning while polling: {e}")

    print("⚠️  Podcast timed out after waiting.")
    return None


# ── Step 6: Download Podcast ───────────────────────────────────────────────────
def download_podcast(artifact_id, env):
    """Download the completed podcast MP3. Returns local file path or None."""
    podcast_dir = Path("podcasts")
    podcast_dir.mkdir(exist_ok=True)
    podcast_path = podcast_dir / f"podcast_{DATE_STR}.mp3"

    print(f"⬇️  Downloading podcast...")
    cmd = ["notebooklm", "download", "audio", str(podcast_path)]
    if artifact_id:
        cmd += ["-a", artifact_id]

    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=180)
    if result.returncode == 0 and podcast_path.exists() and podcast_path.stat().st_size > 0:
        size_mb = podcast_path.stat().st_size / (1024 * 1024)
        print(f"✅ Downloaded: {podcast_path} ({size_mb:.1f} MB)")
        return str(podcast_path)
    else:
        print(f"❌ Download failed:\n{result.stderr}")
        return None


# ── Step 7: Upload Podcast to GitHub Release ───────────────────────────────────
def upload_to_github_release(podcast_path, env):
    """Upload podcast MP3 as a GitHub Release asset.
    Returns direct download URL or None."""
    tag    = f"weekly-{DATE_STR}"
    repo   = env.get("GITHUB_REPOSITORY", "")
    server = env.get("GITHUB_SERVER_URL", "https://github.com")

    if not repo:
        print("⚠️  GITHUB_REPOSITORY not set — cannot create release")
        return None

    print(f"📤 Uploading podcast to GitHub Release '{tag}'...")
    result = subprocess.run([
        "gh", "release", "create", tag, podcast_path,
        "--title", f"📚 פודקאסט שבועי — {DATE_STR}",
        "--notes",
        f"סקירת ספרות שבועית בפסיכיאטריה של הילד והמתבגר — {DATE_STR}\n\n"
        f"*נוצר אוטומטית על ידי GitHub Actions*",
        "--repo", repo,
    ], capture_output=True, text=True, env=env, timeout=180)

    if result.returncode != 0:
        print(f"❌ Release creation failed:\n{result.stderr}")
        return None

    # Retrieve the direct download URL
    view = subprocess.run([
        "gh", "release", "view", tag,
        "--json", "assets",
        "--jq", ".assets[0].browserDownloadUrl",
        "--repo", repo,
    ], capture_output=True, text=True, env=env, timeout=30)

    url = view.stdout.strip()
    if url:
        print(f"✅ Podcast URL: {url}")
        return url

    # Fallback: construct expected URL
    filename = Path(podcast_path).name
    return f"{server}/{repo}/releases/download/{tag}/{filename}"


# ── Step 8: Push Notification via ntfy.sh ─────────────────────────────────────
def send_notification(article_count, nb_url, podcast_url, summary_path, env):
    topic = env.get("NTFY_TOPIC")
    if not topic:
        print("⚠️  NTFY_TOPIC not set — skipping notification")
        return

    print("📱 Sending push notification...")

    body_lines = [f"נמצאו {article_count} מאמרים חדשים השבוע."]
    if nb_url:
        body_lines.append("המחברת מוכנה לעיון ולצ'אט עם AI.")
    if podcast_url:
        body_lines.append("הפודקאסט מוכן להאזנה.")

    # Clickable action buttons in the notification
    actions = []
    if podcast_url:
        actions.append(f"view, 🎙️ האזן לפודקאסט, {podcast_url}")
    if nb_url:
        actions.append(f"view, 📓 פתח מחברת NotebookLM, {nb_url}")

    github_repo   = env.get("GITHUB_REPOSITORY", "")
    github_server = env.get("GITHUB_SERVER_URL", "https://github.com")
    if github_repo and summary_path:
        summary_url = f"{github_server}/{github_repo}/blob/main/{summary_path}"
        actions.append(f"view, 📄 קרא סיכום מלא, {summary_url}")

    headers = {
        "Title":    f"📚 סקירת ספרות שבועית — {DATE_STR}",
        "Tags":     "books,white_check_mark",
        "Priority": "default",
    }
    if actions:
        headers["Actions"] = "; ".join(actions)

    try:
        r = requests.post(
            f"https://ntfy.sh/{topic}",
            data="\n".join(body_lines).encode("utf-8"),
            headers=headers,
            timeout=15,
        )
        print(f"✅ Notification sent (status {r.status_code})")
    except Exception as e:
        print(f"❌ Notification failed: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"📚 Weekly Psychiatry Literature Review — {DATE_STR}")
    print(f"{sep}\n")

    env = os.environ.copy()
    has_notebooklm = bool(env.get("NOTEBOOKLM_AUTH_JSON"))

    # 1. Search PubMed
    articles = search_pubmed()
    if not articles:
        send_notification(0, None, None, None, env)
        sys.exit(1)

    # 2. Fetch abstracts
    articles = fetch_abstracts(articles)

    # 3. Create markdown summary
    summary_path = create_summary(articles)

    nb_url      = None
    podcast_url = None

    if has_notebooklm:
        # 4. Create notebook, add sources, generate briefing doc
        nb_url, nb_id = create_notebook_and_briefing(articles, env)

        if nb_id:
            # 5. Generate podcast and WAIT until it is fully ready
            artifact_id = generate_and_wait_for_podcast(env)

            if artifact_id:
                # 6. Download the finished podcast
                podcast_path = download_podcast(artifact_id, env)

                if podcast_path:
                    # 7. Upload to GitHub Release → get direct MP3 link
                    podcast_url = upload_to_github_release(podcast_path, env)
    else:
        print("⚠️  NOTEBOOKLM_AUTH_JSON not set — skipping NotebookLM & podcast")

    # 8. Send notification (only now, when everything is ready)
    send_notification(len(articles), nb_url, podcast_url, summary_path, env)

    print(f"\n{sep}")
    print("✅ All done!")
    print(f"  Articles  : {len(articles)}")
    print(f"  Summary   : {summary_path}")
    print(f"  Notebook  : {nb_url or '—'}")
    print(f"  Podcast   : {podcast_url or '—'}")
    print(f"{sep}\n")


if __name__ == "__main__":
    main()
