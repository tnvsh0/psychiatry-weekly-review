#!/usr/bin/env python3
"""
Psychiatry Weekly Review — Web UI
Browse weekly articles, listen to podcasts, generate custom podcasts.
"""

import os
import re
import json
import time
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

import requests
import streamlit as st

# ── Config ─────────────────────────────────────────────────────────────────────
GITHUB_REPO  = os.environ.get("GH_REPO", "tnvsh0/psychiatry-weekly-review")
AUTH_JSON    = os.environ.get("NOTEBOOKLM_AUTH_JSON", "")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
GH_TOKEN     = os.environ.get("GH_TOKEN", "")

# Write NotebookLM auth to disk once on startup
if AUTH_JSON:
    storage_path = Path.home() / ".notebooklm" / "storage_state.json"
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    if not storage_path.exists():
        storage_path.write_text(AUTH_JSON, encoding="utf-8")

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Psychiatry Weekly Review",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .full-text-badge { background:#d4edda;color:#155724;padding:2px 8px;border-radius:12px;font-size:0.8em; }
    .abstract-badge  { background:#fff3cd;color:#856404;padding:2px 8px;border-radius:12px;font-size:0.8em; }
    .topic-header    { font-size:1.1em;font-weight:600;margin-top:8px; }
</style>
""", unsafe_allow_html=True)

# ── Password gate ──────────────────────────────────────────────────────────────
if APP_PASSWORD:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        st.title("📚 Psychiatry Weekly Review")
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            if pwd == APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        st.stop()


# ── GitHub helpers ─────────────────────────────────────────────────────────────
def gh_headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if GH_TOKEN:
        h["Authorization"] = f"Bearer {GH_TOKEN}"
    return h


@st.cache_data(ttl=1800)
def list_dates() -> list[str]:
    """List all available weekly dates from summaries/ directory."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/summaries"
    try:
        r = requests.get(url, headers=gh_headers(), timeout=15)
        if r.status_code == 200:
            return sorted(
                [x["name"] for x in r.json() if x["type"] == "dir"],
                reverse=True,
            )
    except Exception:
        pass
    return []


@st.cache_data(ttl=1800)
def load_articles(date: str) -> list[dict]:
    """Load articles.json for a date. Falls back to parsing markdown summaries."""
    base = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/summaries/{date}"

    # Try articles.json first (available after the new pipeline)
    try:
        r = requests.get(f"{base}/articles.json", timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass

    # Fall back: parse markdown files
    return _parse_markdown_summaries(date)


def _parse_markdown_summaries(date: str) -> list[dict]:
    """Parse existing markdown summaries into article dicts (best-effort)."""
    topic_files = {
        "child_adolescent": ("פסיכיאטריה של הילד והמתבגר", "Child & Adolescent Psychiatry"),
        "general_psychiatry": ("פסיכיאטריה כללית", "General Psychiatry"),
        "child_development": ("התפתחות הילד", "Child Development"),
        "neuroscience": ("מדעי המוח ונוירופסיכולוגיה", "Neuroscience"),
        "psychotherapy": ("פסיכותרפיה והתערבויות", "Psychotherapy & Interventions"),
    }
    articles = []
    base = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/summaries/{date}"

    for topic_id, (topic_he, topic_en) in topic_files.items():
        try:
            r = requests.get(f"{base}/{topic_id}.md", timeout=15)
            if r.status_code != 200:
                continue
            text = r.text

            # Extract article blocks (### Title ... --- pattern)
            blocks = re.split(r"\n---\n", text)
            for block in blocks:
                title_m = re.search(r"^### (.+)$", block, re.MULTILINE)
                if not title_m:
                    continue
                title = title_m.group(1).strip()

                journal_m = re.search(r"\*\*כתב עת:\*\* [^|]+ \| \*\*מחברים:\*\* ([^|]+) \| \*\*תאריך:\*\* (.+)", block)
                url_m     = re.search(r"https://pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/", block)
                if_m      = re.search(r"IF: ([\d.]+)", block)

                pmid      = url_m.group(1) if url_m else f"{topic_id}_{len(articles)}"
                url       = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if url_m else ""
                if_val    = float(if_m.group(1)) if if_m else 0.0
                authors   = journal_m.group(1).strip() if journal_m else ""
                pub_date  = journal_m.group(2).strip() if journal_m else ""

                # Abstract: text between meta line and PubMed link
                abstract_m = re.search(r"\n\n(.+?)\n\n🔗", block, re.DOTALL)
                abstract   = abstract_m.group(1).strip() if abstract_m else ""

                articles.append({
                    "pmid": pmid, "title": title,
                    "journal": "", "authors": authors, "pub_date": pub_date,
                    "url": url, "impact_factor": if_val,
                    "abstract": abstract, "has_full_text": False, "pmc_id": None,
                    "topic_id": topic_id, "topic_he": topic_he, "topic_en": topic_en,
                })
        except Exception:
            continue

    return articles


@st.cache_data(ttl=1800)
def load_podcasts(date: str) -> list[dict]:
    """Return list of {topic_id, label_he, label_en, audio_url, nb_url} for a date."""
    topic_ids = ["child_adolescent", "general_psychiatry", "child_development",
                 "neuroscience", "psychotherapy"]
    topic_labels = {
        "child_adolescent":  ("פסיכיאטריה של הילד והמתבגר", "Child & Adolescent Psychiatry"),
        "general_psychiatry":("פסיכיאטריה כללית",           "General Psychiatry"),
        "child_development": ("התפתחות הילד",               "Child Development"),
        "neuroscience":      ("מדעי המוח ונוירופסיכולוגיה", "Neuroscience"),
        "psychotherapy":     ("פסיכותרפיה והתערבויות",      "Psychotherapy & Interventions"),
    }
    results = []
    api = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
    try:
        r = requests.get(api, headers=gh_headers(), timeout=15)
        releases = {rel["tag_name"]: rel for rel in r.json()} if r.status_code == 200 else {}
    except Exception:
        releases = {}

    for tid in topic_ids:
        tag   = f"weekly-{date}-{tid}"
        label_he, label_en = topic_labels[tid]
        rel   = releases.get(tag, {})
        assets = rel.get("assets", [])
        audio_url = assets[0]["browser_download_url"] if assets else None
        results.append({
            "topic_id": tid,
            "label_he": label_he,
            "label_en": label_en,
            "audio_url": audio_url,
            "tag": tag,
        })
    return results


def if_badge(impact_factor: float) -> str:
    if impact_factor >= 15: return "⭐"
    if impact_factor >= 5:  return "🔷"
    return "📄"


# ── Custom podcast ─────────────────────────────────────────────────────────────
def generate_custom_podcast(selected: list[dict], prompt: str) -> str | None:
    date_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    title    = f"Custom Podcast — {date_str}"

    lines = [f"# {title}\n", f"{len(selected)} articles selected for focused discussion.\n", "---\n"]
    for a in selected:
        text_type = "Full Text" if a.get("has_full_text") else "Abstract"
        lines += [
            f"## {a['title']}",
            f"**Journal:** {a.get('journal','')}  |  IF {a.get('impact_factor',0):.1f}  |  {text_type}",
            f"**Authors:** {a.get('authors','')} ({a.get('pub_date','')})",
            f"**PubMed:** {a.get('url','')}\n",
            a.get("abstract", "(No text available)"),
            "\n---\n",
        ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("\n".join(lines))
        tmp_path = f.name

    env = os.environ.copy()

    result = subprocess.run(
        ["notebooklm", "create", title, "--json"],
        capture_output=True, text=True, env=env, timeout=60,
    )
    if result.returncode != 0:
        st.error(f"Could not create notebook: {result.stderr[:300]}")
        return None
    try:
        nb_data = json.loads(result.stdout.strip())
        nb_id   = (nb_data.get("notebook") or nb_data).get("id")
    except Exception:
        st.error("Could not parse notebook ID.")
        return None

    nb_url = f"https://notebooklm.google.com/notebook/{nb_id}"
    subprocess.run(["notebooklm", "use", nb_id], capture_output=True, env=env, timeout=30)
    subprocess.run(
        ["notebooklm", "source", "add", tmp_path, "--json"],
        capture_output=True, env=env, timeout=120,
    )
    Path(tmp_path).unlink(missing_ok=True)

    st.info("Source uploaded. Waiting 40s for indexing...")
    time.sleep(40)

    subprocess.run([
        "notebooklm", "generate", "audio", prompt,
        "--format", "deep-dive", "--language", "he", "--json",
    ], capture_output=True, text=True, env=env, timeout=60)

    return nb_url


# ══════════════════════════════════════════════════════════════════════════════
# MAIN UI
# ══════════════════════════════════════════════════════════════════════════════
st.title("📚 Psychiatry Weekly Review")

dates = list_dates()
if not dates:
    st.warning("No weekly reviews found yet.")
    st.stop()

# Date selector in sidebar
with st.sidebar:
    st.header("Filters")
    selected_date = st.selectbox("Week", dates, index=0)
    st.divider()
    min_if       = st.slider("Min Impact Factor", 0.0, 30.0, 0.0, 0.5)
    text_filter  = st.selectbox("Text type", ["All", "Full text only", "Abstract only"])
    search       = st.text_input("Search title / text", placeholder="ADHD, CBT...")
    st.divider()
    st.caption(f"[GitHub repo](https://github.com/{GITHUB_REPO})")

articles = load_articles(selected_date)
podcasts = load_podcasts(selected_date)

full_text_n = sum(1 for a in articles if a.get("has_full_text"))
st.caption(
    f"**{selected_date}** · {len(articles)} articles · "
    f"📖 {full_text_n} full text · 📋 {len(articles)-full_text_n} abstract"
)

# ── TAB LAYOUT ─────────────────────────────────────────────────────────────────
tab_podcasts, tab_articles, tab_custom = st.tabs([
    "🎙️ Weekly Podcasts",
    "📋 Articles",
    "✨ Custom Podcast",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: Weekly Podcasts
# ══════════════════════════════════════════════════════════════════════════════
with tab_podcasts:
    st.subheader(f"Podcasts — week of {selected_date}")

    any_podcast = any(p["audio_url"] for p in podcasts)
    if not any_podcast:
        st.info(
            "No podcasts uploaded yet for this week.\n\n"
            "Podcasts are generated automatically every Sunday and uploaded to GitHub Releases. "
            "They will appear here after the next run."
        )

    cols = st.columns(2)
    for i, p in enumerate(podcasts):
        with cols[i % 2]:
            st.markdown(f"**{p['label_he']}**")
            st.caption(p["label_en"])
            if p["audio_url"]:
                try:
                    audio_r = requests.get(p["audio_url"], timeout=30)
                    if audio_r.status_code == 200:
                        st.audio(audio_r.content, format="audio/mp3")
                    else:
                        st.markdown(f"[Download MP3 ↗]({p['audio_url']})")
                except Exception:
                    st.markdown(f"[Download MP3 ↗]({p['audio_url']})")
            else:
                st.caption("_(not available yet)_")
            st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: Articles
# ══════════════════════════════════════════════════════════════════════════════
with tab_articles:
    if not articles:
        st.info(
            "Article list not available for this week yet.\n\n"
            "The structured article list (`articles.json`) is generated starting from the next "
            "weekly run. Previous weeks' summaries are available as Markdown on GitHub:\n\n"
            f"[View summaries on GitHub](https://github.com/{GITHUB_REPO}/tree/main/summaries/{selected_date})"
        )
    else:
        # Filter
        filtered = articles
        if min_if > 0:
            filtered = [a for a in filtered if a.get("impact_factor", 0) >= min_if]
        if text_filter == "Full text only":
            filtered = [a for a in filtered if a.get("has_full_text")]
        elif text_filter == "Abstract only":
            filtered = [a for a in filtered if not a.get("has_full_text")]
        if search:
            q = search.lower()
            filtered = [a for a in filtered
                        if q in a["title"].lower() or q in a.get("abstract", "").lower()]

        st.caption(f"{len(filtered)} articles · select any to generate a custom podcast")

        # Store selections in session state
        if "selected_pmids" not in st.session_state:
            st.session_state.selected_pmids = set()

        all_topics = sorted(set(a["topic_he"] for a in filtered))
        for topic_he in all_topics:
            topic_articles = [a for a in filtered if a["topic_he"] == topic_he]
            if not topic_articles:
                continue

            with st.expander(f"**{topic_he}** — {len(topic_articles)} articles", expanded=True):
                for a in topic_articles:
                    pmid     = a["pmid"]
                    if_val   = a.get("impact_factor", 0)
                    has_full = a.get("has_full_text", False)
                    text_tag = (
                        '<span class="full-text-badge">📖 Full text</span>'
                        if has_full else
                        '<span class="abstract-badge">📋 Abstract</span>'
                    )

                    col_cb, col_content = st.columns([0.04, 0.96])
                    with col_cb:
                        checked = st.checkbox(
                            "", key=f"sel_{pmid}",
                            value=(pmid in st.session_state.selected_pmids),
                            label_visibility="collapsed",
                        )
                        if checked:
                            st.session_state.selected_pmids.add(pmid)
                        else:
                            st.session_state.selected_pmids.discard(pmid)

                    with col_content:
                        st.markdown(
                            f"{if_badge(if_val)} **{a['title']}** &nbsp; {text_tag}",
                            unsafe_allow_html=True,
                        )
                        meta = []
                        if a.get("journal"): meta.append(a["journal"])
                        if if_val > 0:       meta.append(f"IF {if_val:.1f}")
                        if a.get("authors"): meta.append(a["authors"])
                        if a.get("pub_date"):meta.append(a["pub_date"])
                        if a.get("url"):     meta.append(f"[PubMed ↗]({a['url']})")
                        st.caption(" · ".join(meta))

                        abstract = a.get("abstract", "")
                        if abstract:
                            with st.expander("Show text"):
                                st.write(abstract[:3000] + ("..." if len(abstract) > 3000 else ""))

        # Floating selection counter
        n_sel = len(st.session_state.selected_pmids)
        if n_sel > 0:
            st.success(
                f"✅ {n_sel} article{'s' if n_sel > 1 else ''} selected — "
                f"go to the **✨ Custom Podcast** tab to generate."
            )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: Custom Podcast
# ══════════════════════════════════════════════════════════════════════════════
with tab_custom:
    st.subheader("Generate a Custom Hebrew Podcast")
    st.caption(
        "Select articles in the Articles tab, then generate a focused podcast "
        "on just those articles. A new NotebookLM notebook is created automatically."
    )

    n_sel = len(st.session_state.get("selected_pmids", set()))

    if n_sel == 0:
        st.info("No articles selected yet. Go to the **📋 Articles** tab and check the articles you want.")
    else:
        selected_articles = [a for a in articles if a["pmid"] in st.session_state.selected_pmids]

        st.markdown(f"**{n_sel} article{'s' if n_sel > 1 else ''} selected:**")
        for a in selected_articles:
            ft = "📖" if a.get("has_full_text") else "📋"
            st.markdown(f"- {ft} **{a['title']}** — *{a.get('journal') or a.get('topic_en','')}*")

        st.divider()
        custom_prompt = st.text_area(
            "Podcast prompt (Hebrew)",
            value=(
                "צור דיון מעמיק ומרתק על המאמרים הנבחרים. "
                "דגש על משמעות קלינית, יישום מעשי, ומה המאמרים מוסיפים לידע הקיים."
            ),
            height=100,
        )

        has_auth = bool(AUTH_JSON) or (Path.home() / ".notebooklm" / "storage_state.json").exists()
        if not has_auth:
            st.warning("NotebookLM auth not available. The app needs NOTEBOOKLM_AUTH_JSON.")
        else:
            if st.button("🚀 Generate Podcast", type="primary"):
                with st.spinner(f"Creating NotebookLM notebook with {n_sel} articles and starting Hebrew podcast (~20 min)..."):
                    nb_url = generate_custom_podcast(selected_articles, custom_prompt)

                if nb_url:
                    st.success("✅ Podcast generation started on Google's servers!")
                    st.markdown(f"### [Open Notebook in NotebookLM ↗]({nb_url})")
                    st.info(
                        "The Hebrew podcast will appear inside the notebook within **15–20 minutes**. "
                        "You can close this page — the generation continues on Google's servers."
                    )
                    # Clear selection after use
                    st.session_state.selected_pmids = set()
                else:
                    st.error("Failed to start podcast. Auth may have expired — run update_auth.ps1.")
