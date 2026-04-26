#!/usr/bin/env python3
"""
Psychiatry Weekly Review — Web UI
Streamlit app for browsing articles and generating custom podcasts.
"""

import os
import json
import time
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

import requests
import streamlit as st

# ── Config ─────────────────────────────────────────────────────────────────────
GITHUB_REPO = os.environ.get("GH_REPO", "tnvsh0/psychiatry-weekly-review")
AUTH_JSON   = os.environ.get("NOTEBOOKLM_AUTH_JSON", "")

# Write auth to disk once on startup
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
    .article-card { border-left: 4px solid #4CAF50; padding: 8px 16px; margin: 8px 0; }
    .if-tier1 { border-left-color: #FFD700; }
    .if-tier2 { border-left-color: #4169E1; }
    .if-tier3 { border-left-color: #808080; }
    .full-text-badge { background: #d4edda; color: #155724; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; }
    .abstract-badge  { background: #fff3cd; color: #856404; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; }
</style>
""", unsafe_allow_html=True)


# ── Data loading ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800)
def load_articles() -> dict:
    """Load the latest articles.json from GitHub."""
    try:
        api = f"https://api.github.com/repos/{GITHUB_REPO}/contents/summaries"
        r = requests.get(api, timeout=15)
        if r.status_code != 200:
            return {}
        dirs = sorted([x["name"] for x in r.json() if x["type"] == "dir"], reverse=True)
        if not dirs:
            return {}
        latest = dirs[0]
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/summaries/{latest}/articles.json"
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return {}
        return {"date": latest, "articles": r.json()}
    except Exception as e:
        st.error(f"Failed to load articles: {e}")
        return {}


@st.cache_data(ttl=1800)
def list_available_dates() -> list[str]:
    """List all available weekly dates."""
    try:
        api = f"https://api.github.com/repos/{GITHUB_REPO}/contents/summaries"
        r = requests.get(api, timeout=15)
        if r.status_code != 200:
            return []
        return sorted([x["name"] for x in r.json() if x["type"] == "dir"], reverse=True)
    except Exception:
        return []


@st.cache_data(ttl=1800)
def load_articles_for_date(date: str) -> list[dict]:
    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/summaries/{date}/articles.json"
    try:
        r = requests.get(url, timeout=15)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []


def if_badge(impact_factor: float) -> str:
    if impact_factor >= 15:
        return "⭐"
    if impact_factor >= 5:
        return "🔷"
    return "📄"


# ── Custom podcast generation ──────────────────────────────────────────────────
def generate_custom_podcast(selected: list[dict], prompt: str) -> str | None:
    """Create a NotebookLM notebook for the selected articles and start a Hebrew podcast."""
    date_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    title    = f"Custom Podcast — {date_str}"

    # Build markdown source document
    lines = [f"# {title}\n", f"Selected {len(selected)} articles for focused discussion.\n", "---\n"]
    for a in selected:
        text_type = "Full Text" if a.get("has_full_text") else "Abstract"
        lines += [
            f"## {a['title']}",
            f"**Journal:** {a['journal']}  |  **IF:** {a.get('impact_factor', 0):.1f}  |  {text_type}",
            f"**Authors:** {a['authors']} ({a['pub_date']})",
            f"**PubMed:** {a['url']}\n",
            a.get("abstract", "(No text available)"),
            "\n---\n",
        ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("\n".join(lines))
        tmp_path = f.name

    env = os.environ.copy()

    # 1. Create notebook
    result = subprocess.run(
        ["notebooklm", "create", title, "--json"],
        capture_output=True, text=True, env=env, timeout=60,
    )
    if result.returncode != 0:
        st.error(f"Could not create notebook: {result.stderr[:300]}")
        return None
    try:
        nb_data = json.loads(result.stdout.strip())
        nb_id = (nb_data.get("notebook") or nb_data).get("id")
    except Exception:
        st.error("Could not parse notebook ID.")
        return None

    nb_url = f"https://notebooklm.google.com/notebook/{nb_id}"

    # 2. Add source
    subprocess.run(["notebooklm", "use", nb_id], capture_output=True, env=env, timeout=30)
    subprocess.run(
        ["notebooklm", "source", "add", tmp_path, "--json"],
        capture_output=True, env=env, timeout=120,
    )
    Path(tmp_path).unlink(missing_ok=True)

    st.info("Source uploaded. Waiting 40s for indexing...")
    time.sleep(40)

    # 3. Start podcast
    result = subprocess.run([
        "notebooklm", "generate", "audio", prompt,
        "--format", "deep-dive", "--language", "he", "--json",
    ], capture_output=True, text=True, env=env, timeout=60)

    return nb_url


# ── Main UI ────────────────────────────────────────────────────────────────────
st.title("📚 Psychiatry Weekly Review")

# Date selector
dates = list_available_dates()
if not dates:
    st.warning("No weekly reviews found yet. Run the Cloud Run job first.")
    st.stop()

selected_date = st.selectbox("Week", dates, index=0)
articles = load_articles_for_date(selected_date)

if not articles:
    st.warning(f"No articles found for {selected_date}.")
    st.stop()

full_text_count = sum(1 for a in articles if a.get("has_full_text"))
st.caption(
    f"**{selected_date}** — {len(articles)} articles · "
    f"📖 {full_text_count} full text (PMC) · "
    f"📋 {len(articles) - full_text_count} abstract only"
)

# ── Sidebar filters ────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")

    all_topics = sorted(set(a["topic_he"] for a in articles))
    selected_topics = st.multiselect("Topics", all_topics, default=all_topics)

    min_if = st.slider("Min Impact Factor", 0.0, 30.0, 0.0, 0.5)

    text_filter = st.selectbox("Text availability", ["All", "Full text only", "Abstract only"])

    search = st.text_input("Search title / abstract", placeholder="e.g. ADHD, CBT...")

    st.divider()
    st.caption(f"Repo: [{GITHUB_REPO}](https://github.com/{GITHUB_REPO})")

# ── Filter ─────────────────────────────────────────────────────────────────────
filtered = articles
if selected_topics:
    filtered = [a for a in filtered if a["topic_he"] in selected_topics]
if min_if > 0:
    filtered = [a for a in filtered if a.get("impact_factor", 0) >= min_if]
if text_filter == "Full text only":
    filtered = [a for a in filtered if a.get("has_full_text")]
elif text_filter == "Abstract only":
    filtered = [a for a in filtered if not a.get("has_full_text")]
if search:
    q = search.lower()
    filtered = [a for a in filtered if q in a["title"].lower() or q in a.get("abstract", "").lower()]

st.markdown(f"**{len(filtered)} articles** matching filters")

# ── Article list with checkboxes ───────────────────────────────────────────────
selected_pmids: set[str] = set()

for topic_he in all_topics:
    topic_articles = [a for a in filtered if a["topic_he"] == topic_he]
    if not topic_articles:
        continue

    with st.expander(f"**{topic_he}** — {len(topic_articles)} articles", expanded=True):
        for a in topic_articles:
            pmid      = a["pmid"]
            if_val    = a.get("impact_factor", 0)
            badge     = if_badge(if_val)
            has_full  = a.get("has_full_text", False)
            text_span = (
                '<span class="full-text-badge">📖 Full text</span>'
                if has_full else
                '<span class="abstract-badge">📋 Abstract</span>'
            )

            col_cb, col_content = st.columns([0.04, 0.96])
            with col_cb:
                checked = st.checkbox("", key=f"sel_{pmid}", label_visibility="collapsed")
                if checked:
                    selected_pmids.add(pmid)

            with col_content:
                st.markdown(
                    f"{badge} **{a['title']}** &nbsp; {text_span}",
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"{a['journal']}  ·  IF {if_val:.1f}  ·  "
                    f"{a['authors']}  ·  {a['pub_date']}  ·  "
                    f"[PubMed ↗]({a['url']})"
                )
                with st.expander("Show text"):
                    text = a.get("abstract", "(Not available)")
                    st.write(text[:3000] + ("..." if len(text) > 3000 else ""))

# ── Custom podcast panel ───────────────────────────────────────────────────────
if selected_pmids:
    st.divider()
    n = len(selected_pmids)
    st.subheader(f"🎙️ Generate Custom Podcast ({n} article{'s' if n > 1 else ''} selected)")

    with st.expander("Selected articles"):
        for a in articles:
            if a["pmid"] in selected_pmids:
                st.markdown(f"- **{a['title']}** — *{a['journal']}*")

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
        st.warning("NotebookLM auth not configured. Set NOTEBOOKLM_AUTH_JSON env var.")
    else:
        if st.button("🚀 Generate Podcast", type="primary"):
            selected_articles = [a for a in articles if a["pmid"] in selected_pmids]
            with st.spinner(f"Creating notebook with {n} articles and starting podcast generation (~20 min total)..."):
                nb_url = generate_custom_podcast(selected_articles, custom_prompt)

            if nb_url:
                st.success("✅ Podcast generation started!")
                st.markdown(f"### [Open Notebook in NotebookLM ↗]({nb_url})")
                st.info(
                    "The Hebrew podcast will appear inside the notebook within **15–20 minutes**. "
                    "You can close this page — the podcast is generated on Google's servers."
                )
            else:
                st.error("Failed to start podcast. Check auth or try again.")
