#!/usr/bin/env python3
"""
Weekly Psychiatry Literature Review — Multi-Topic Edition
──────────────────────────────────────────────────────────
For each topic:
  1. Search PubMed — journal-specific queries first (guarantees top journals),
     then broad MeSH queries as supplement
  2. Fetch abstracts
  3. Create a markdown summary (sorted by Impact Factor)
  4. Create a dedicated NotebookLM notebook
  5. Upload the summary as source
  6. Generate a Hebrew podcast (all topics start in parallel on Google's side)
  7. Download + upload each podcast to a GitHub Release
  8. Send one ntfy notification with links to everything

IMPORTANT: Never fabricates articles — only real PubMed data is used.
"""

import os
import sys
import json
import time
import subprocess
import requests
from datetime import datetime, timedelta
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────────────────
PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
TODAY       = datetime.utcnow()
DATE_STR    = TODAY.strftime("%Y-%m-%d")
WEEK_START  = TODAY - timedelta(days=7)

# ── Journal Impact Factors (2023-2024 approximate) ─────────────────────────────
# Tier 1 >= 15  |  Tier 2 >= 5  |  Tier 3 < 5 (or unknown -> 0)
JOURNAL_IF: dict[str, float] = {
    # Tier 1
    "jama psychiatry":                                          25.8,
    "jama":                                                    120.7,
    "new england journal of medicine":                          96.2,
    "n engl j med":                                             96.2,
    "lancet":                                                   99.5,
    "lancet psychiatry":                                        64.3,
    "nature medicine":                                          87.2,
    "nature":                                                   69.5,
    "science":                                                  67.2,
    "world psychiatry":                                         73.3,
    "bmj":                                                     105.7,
    "nature neuroscience":                                      25.0,
    "jama pediatrics":                                          27.6,
    "american journal of psychiatry":                           18.1,
    "am j psychiatry":                                          18.1,
    "annals of internal medicine":                              39.2,
    "brain":                                                    14.5,
    # Tier 2
    "molecular psychiatry":                                     13.4,
    "biological psychiatry":                                    12.8,
    "jaacap":                                                   10.2,
    "journal of the american academy of child and adolescent psychiatry": 10.2,
    "j am acad child adolesc psychiatry":                       10.2,
    "neuropsychopharmacology":                                   8.0,
    "pediatrics":                                                8.0,
    "journal of neuroscience":                                   6.7,
    "schizophrenia bulletin":                                    7.4,
    "journal of child psychology and psychiatry":                7.2,
    "j child psychol psychiatry":                                7.2,
    "acta psychiatrica scandinavica":                            6.7,
    "psychological medicine":                                    6.0,
    "european child and adolescent psychiatry":                  6.0,
    "eur child adolesc psychiatry":                              6.0,
    "depression and anxiety":                                    6.0,
    "european neuropsychopharmacology":                          5.5,
    "j consult clin psychol":                                    5.2,
    "journal of consulting and clinical psychology":             5.2,
    "behav res ther":                                            5.0,
    "behaviour research and therapy":                            5.0,
    # Tier 3
    "journal of autism and developmental disorders":             4.0,
    "j autism dev disord":                                       4.0,
    "psychopharmacology":                                        4.0,
    "frontiers in neuroscience":                                 4.0,
    "journal of abnormal child psychology":                      4.2,
    "j abnorm child psychol":                                    4.2,
    "psychiatry research":                                       3.8,
    "journal of attention disorders":                            3.5,
    "child psychiatry and human development":                    3.5,
    "comprehensive psychiatry":                                  3.5,
    "frontiers in psychiatry":                                   3.2,
    "child and adolescent psychiatry and mental health":          3.0,
    "journal of developmental and behavioral pediatrics":         3.0,
    "j child adolesc psychopharmacol":                           3.5,
    "journal of child and adolescent psychopharmacology":        3.5,
    "dev med child neurol":                                      4.5,
    "developmental medicine and child neurology":                4.5,
    "dev psychopathol":                                          4.8,
    "development and psychopathology":                           4.8,
    "child dev":                                                 4.7,
    "child development":                                         4.7,
}


def get_journal_if(journal_name: str) -> float:
    """Return impact factor (case-insensitive substring match). 0.0 if unknown."""
    name = journal_name.lower().strip()
    if name in JOURNAL_IF:
        return JOURNAL_IF[name]
    best_val, best_len = 0.0, 0
    for key, val in JOURNAL_IF.items():
        if key in name or name in key:
            if len(key) > best_len:
                best_val, best_len = val, len(key)
    return best_val


def if_badge(impact_factor: float) -> str:
    if impact_factor >= 15:
        return "\u2b50"   # star
    if impact_factor >= 5:
        return "\U0001f537"  # blue diamond
    return "\U0001f4c4"   # page


# ── Topic Definitions ──────────────────────────────────────────────────────────
# Each topic:
#   journals  -- searched directly (guarantees top journals are always included)
#   broad     -- supplemental queries (MeSH + filtered high-impact journals)
#   max_articles, podcast_prompt
TOPICS = [
    {
        # ── CLUSTER 1 ───────────────────────────────────────────────────────────
        # Primary journals of child & adolescent psychiatry (ALL new articles)
        # PLUS relevant articles filtered from top-tier general/pediatric journals
        "id":       "child_adolescent",
        "label_en": "Child & Adolescent Psychiatry",
        "label_he": "\u05e4\u05e1\u05d9\u05db\u05d9\u05d0\u05d8\u05e8\u05d9\u05d4 \u05e9\u05dc \u05d4\u05d9\u05dc\u05d3 \u05d5\u05d4\u05de\u05ea\u05d1\u05d2\u05e8",
        "journals": [
            "J Am Acad Child Adolesc Psychiatry",   # JAACAP — the flagship journal
            "J Child Psychol Psychiatry",            # JCPP
            "Child Adolesc Mental Health",           # CAMH
            "Eur Child Adolesc Psychiatry",          # ECAP
        ],
        "broad": [
            # High-impact general psychiatry journals — filtered for child/adolescent content
            '"JAMA Psychiatry"[Journal] AND ("child"[MeSH] OR "adolescent"[MeSH] OR "youth"[Title/Abstract])',
            '"Lancet Psychiatry"[Journal] AND ("child"[MeSH] OR "adolescent"[MeSH] OR "youth"[Title/Abstract])',
            # Top pediatric journals — filtered for mental health / neurodevelopment
            '"JAMA Pediatr"[Journal] AND ("mental health"[Title/Abstract] OR "psychiatry"[Title/Abstract] OR "neurodevelopment"[Title/Abstract] OR "autism"[Title/Abstract] OR "ADHD"[Title/Abstract])',
            '"Lancet"[Journal] AND ("child psychiatry"[Title/Abstract] OR "adolescent psychiatry"[Title/Abstract] OR "autism"[Title/Abstract] OR "ADHD"[Title/Abstract] OR "mental health"[Title/Abstract])',
            '"N Engl J Med"[Journal] AND ("child"[MeSH] OR "adolescent"[MeSH]) AND ("psychiatry"[Title/Abstract] OR "mental health"[Title/Abstract] OR "autism"[Title/Abstract] OR "ADHD"[Title/Abstract])',
            # Broad MeSH fallback
            '"child psychiatry"[MeSH] OR "adolescent psychiatry"[MeSH]',
            '"autism spectrum disorder"[MeSH] AND ("child"[MeSH] OR "adolescent"[MeSH])',
            '"attention deficit disorder with hyperactivity"[MeSH]',
            '"anxiety disorders"[MeSH] AND ("child"[MeSH] OR "adolescent"[MeSH])',
            '"depressive disorder"[MeSH] AND ("child"[MeSH] OR "adolescent"[MeSH])',
            '"eating disorders"[MeSH] AND "adolescent"[MeSH]',
            '"self-injurious behavior"[MeSH] AND "adolescent"[MeSH]',
            '"conduct disorder"[MeSH] OR "oppositional defiant disorder"[Title/Abstract]',
        ],
        "max_articles": 20,
        "podcast_prompt": (
            "\u05e6\u05d5\u05e8 \u05d3\u05d9\u05d5\u05df \u05de\u05e2\u05de\u05d9\u05e7 \u05d5\u05de\u05e8\u05ea\u05e7 \u05e2\u05dc \u05d4\u05de\u05de\u05e6\u05d0\u05d9\u05dd \u05d4\u05de\u05e9\u05de\u05e2\u05d5\u05ea\u05d9\u05d9\u05dd \u05d1\u05d9\u05d5\u05ea\u05e8 \u05e9\u05dc \u05d4\u05e9\u05d1\u05d5\u05e2 "
            "\u05d1\u05e4\u05e1\u05d9\u05db\u05d9\u05d0\u05d8\u05e8\u05d9\u05d4 \u05e9\u05dc \u05d4\u05d9\u05dc\u05d3 \u05d5\u05d4\u05de\u05ea\u05d1\u05d2\u05e8. \u05d3\u05d2\u05e9 \u05e2\u05dc \u05e8\u05dc\u05d5\u05d5\u05e0\u05d8\u05d9\u05d5\u05ea \u05e7\u05dc\u05d9\u05e0\u05d9\u05ea, "
            "\u05d2\u05d9\u05e9\u05d5\u05ea \u05d8\u05d9\u05e4\u05d5\u05dc\u05d9\u05d5\u05ea \u05d7\u05d3\u05e9\u05d5\u05ea, \u05d5\u05de\u05e9\u05de\u05e2\u05d5\u05ea \u05d4\u05de\u05de\u05e6\u05d0\u05d9\u05dd \u05dc\u05de\u05ea\u05de\u05d7\u05d4 \u05d1\u05e4\u05e1\u05d9\u05db\u05d9\u05d0\u05d8\u05e8\u05d9\u05d4."
        ),
    },
    {
        # ── CLUSTER 2 ───────────────────────────────────────────────────────────
        # Top-tier general psychiatry journals — adults, high-impact research
        "id":       "general_psychiatry",
        "label_en": "General Psychiatry — High Impact",
        "label_he": "\u05e4\u05e1\u05d9\u05db\u05d9\u05d0\u05d8\u05e8\u05d9\u05d4 \u05db\u05dc\u05dc\u05d9\u05ea",
        "journals": [
            "World Psychiatry",
            "JAMA Psychiatry",
            "Am J Psychiatry",
            "Mol Psychiatry",
            "Lancet Psychiatry",
        ],
        "broad": [
            # NEJM filtered for psychiatry
            '"N Engl J Med"[Journal] AND ("psychiatry"[Title/Abstract] OR "mental health"[Title/Abstract] OR "schizophrenia"[Title/Abstract] OR "depression"[Title/Abstract] OR "bipolar"[Title/Abstract])',
            # Broad topic coverage
            '("schizophrenia"[MeSH] OR "bipolar disorder"[MeSH]) AND ("randomized controlled trial"[pt] OR "meta-analysis"[pt])',
            '"depressive disorder, major"[MeSH] AND ("randomized controlled trial"[pt] OR "meta-analysis"[pt])',
            '"suicide"[MeSH] AND ("prevention"[Title/Abstract] OR "risk factors"[Title/Abstract])',
            '"psychosis"[Title/Abstract] AND "first episode"[Title/Abstract]',
            '"borderline personality disorder"[MeSH] AND ("treatment"[Title/Abstract] OR "therapy"[Title/Abstract])',
        ],
        "max_articles": 15,
        "podcast_prompt": (
            "\u05e6\u05d5\u05e8 \u05d3\u05d9\u05d5\u05df \u05de\u05e2\u05de\u05d9\u05e7 \u05e2\u05dc \u05d4\u05de\u05de\u05e6\u05d0\u05d9\u05dd \u05d4\u05de\u05e9\u05de\u05e2\u05d5\u05ea\u05d9\u05d9\u05dd \u05d1\u05d9\u05d5\u05ea\u05e8 \u05d4\u05e9\u05d1\u05d5\u05e2 \u05d1\u05e4\u05e1\u05d9\u05db\u05d9\u05d0\u05d8\u05e8\u05d9\u05d4 \u05d4\u05db\u05dc\u05dc\u05d9\u05ea. "
            "\u05d3\u05d2\u05e9 \u05e2\u05dc \u05de\u05de\u05e6\u05d0\u05d9\u05dd \u05e9\u05de\u05e9\u05e0\u05d9\u05dd \u05d0\u05ea \u05d4\u05e4\u05e8\u05e7\u05d8\u05d9\u05e7\u05d4 \u05d4\u05e7\u05dc\u05d9\u05e0\u05d9\u05ea \u05d5\u05e8\u05dc\u05d5\u05d5\u05e0\u05d8\u05d9\u05d9\u05dd \u05d2\u05dd \u05dc\u05e4\u05e1\u05d9\u05db\u05d9\u05d0\u05d8\u05e8\u05d9\u05d9\u05ea \u05d9\u05dc\u05d3\u05d9\u05dd."
        ),
    },
    {
        # ── CLUSTER 3 ───────────────────────────────────────────────────────────
        # Child development — developmental science, early childhood, parenting
        "id":       "child_development",
        "label_en": "Child Development",
        "label_he": "\u05d4\u05ea\u05e4\u05ea\u05d7\u05d5\u05ea \u05d4\u05d9\u05dc\u05d3",
        "journals": [
            "Child Dev",
            "Dev Psychopathol",
            "J Abnorm Child Psychol",
            "Infant Ment Health J",
            "Dev Sci",
        ],
        "broad": [
            '"child development"[MeSH] AND ("mental health"[Title/Abstract] OR "behavior disorders"[MeSH] OR "psychopathology"[Title/Abstract])',
            '"adverse childhood experiences"[Title/Abstract]',
            '"parenting"[MeSH] AND ("child behavior"[MeSH] OR "mental health"[Title/Abstract])',
            '"attachment behavior"[MeSH]',
            '"early intervention"[MeSH] AND ("child"[MeSH] OR "infant"[MeSH])',
            '"social-emotional development"[Title/Abstract]',
            '"trauma"[Title/Abstract] AND ("child"[MeSH] OR "infant"[MeSH])',
        ],
        "max_articles": 15,
        "podcast_prompt": (
            "\u05e6\u05d5\u05e8 \u05d3\u05d9\u05d5\u05df \u05de\u05e2\u05de\u05d9\u05e7 \u05e2\u05dc \u05d4\u05de\u05de\u05e6\u05d0\u05d9\u05dd \u05d4\u05d7\u05e9\u05d5\u05d1\u05d9\u05dd \u05d1\u05d9\u05d5\u05ea\u05e8 \u05d4\u05e9\u05d1\u05d5\u05e2 \u05d1\u05ea\u05d7\u05d5\u05dd "
            "\u05d4\u05ea\u05e4\u05ea\u05d7\u05d5\u05ea \u05d4\u05d9\u05dc\u05d3. \u05d3\u05d2\u05e9 \u05e2\u05dc \u05de\u05e9\u05de\u05e2\u05d5\u05ea \u05e7\u05dc\u05d9\u05e0\u05d9\u05ea \u05dc\u05de\u05ea\u05de\u05d7\u05d4 \u05d1\u05e4\u05e1\u05d9\u05db\u05d9\u05d0\u05d8\u05e8\u05d9\u05d4 \u05e9\u05dc \u05d4\u05d9\u05dc\u05d3."
        ),
    },
    {
        # ── CLUSTER 4 ───────────────────────────────────────────────────────────
        # Neuroscience, neurobiology, neuropsychology — relevant to psychiatry
        "id":       "neuroscience",
        "label_en": "Neuroscience & Neuropsychology",
        "label_he": "\u05de\u05d3\u05e2\u05d9 \u05d4\u05de\u05d5\u05d7 \u05d5\u05e0\u05d5\u05d9\u05e8\u05d5\u05e4\u05e1\u05d9\u05db\u05d5\u05dc\u05d5\u05d2\u05d9\u05d4",
        "journals": [
            "Nat Neurosci",
            "Neuron",
            "Brain",
            "J Neurosci",
            "Neuropsychopharmacology",
        ],
        "broad": [
            # Filtered for psychiatric/developmental relevance
            '"Nature Neuroscience"[Journal] AND ("psychiatry"[Title/Abstract] OR "depression"[Title/Abstract] OR "schizophrenia"[Title/Abstract] OR "autism"[Title/Abstract] OR "development"[Title/Abstract])',
            '"brain development"[MeSH] AND ("child"[MeSH] OR "adolescent"[MeSH])',
            '"prefrontal cortex"[MeSH] AND ("adolescent"[MeSH] OR "development"[Title/Abstract])',
            '"neuroplasticity"[MeSH] AND ("psychiatric disorders"[Title/Abstract] OR "mental health"[Title/Abstract])',
            '"cognitive development"[MeSH] AND ("child"[MeSH] OR "adolescent"[MeSH])',
            '"executive function"[Title/Abstract] AND ("child"[MeSH] OR "adolescent"[MeSH])',
            '"stress"[MeSH] AND ("brain"[Title/Abstract] OR "neurobiology"[Title/Abstract]) AND ("child"[MeSH] OR "adolescent"[MeSH])',
        ],
        "max_articles": 12,
        "podcast_prompt": (
            "\u05e6\u05d5\u05e8 \u05d3\u05d9\u05d5\u05df \u05de\u05e2\u05de\u05d9\u05e7 \u05e2\u05dc \u05d4\u05de\u05de\u05e6\u05d0\u05d9\u05dd \u05d4\u05d7\u05e9\u05d5\u05d1\u05d9\u05dd \u05d1\u05d9\u05d5\u05ea\u05e8 \u05d4\u05e9\u05d1\u05d5\u05e2 \u05d1\u05ea\u05d7\u05d5\u05dd \u05de\u05d3\u05e2\u05d9 \u05d4\u05de\u05d5\u05d7 \u05d5\u05e0\u05d5\u05d9\u05e8\u05d5\u05e4\u05e1\u05d9\u05db\u05d5\u05dc\u05d5\u05d2\u05d9\u05d4. "
            "\u05d3\u05d2\u05e9 \u05e2\u05dc \u05de\u05e9\u05de\u05e2\u05d5\u05ea \u05dc\u05e4\u05e1\u05d9\u05db\u05d9\u05d0\u05d8\u05e8\u05d9\u05d4 \u05e9\u05dc \u05d4\u05d9\u05dc\u05d3 \u05d5\u05dc\u05d4\u05d1\u05e0\u05ea \u05d4\u05de\u05e0\u05d2\u05e0\u05d5\u05e0\u05d9\u05dd \u05d4\u05e2\u05e6\u05d1\u05d9\u05d9\u05dd."
        ),
    },
    {
        # ── CLUSTER 5 ───────────────────────────────────────────────────────────
        # Psychotherapy — children AND adults, evidence-based treatments
        "id":       "psychotherapy",
        "label_en": "Psychotherapy & Interventions",
        "label_he": "\u05e4\u05e1\u05d9\u05db\u05d5\u05ea\u05e8\u05e4\u05d9\u05d4 \u05d5\u05d4\u05ea\u05e2\u05e8\u05d1\u05d5\u05d9\u05d5\u05ea",
        "journals": [
            "J Consult Clin Psychol",
            "Behav Res Ther",
            "Psychother Psychosom",
            "Clin Child Fam Psychol Rev",
            "Psychol Med",
        ],
        "broad": [
            '"psychotherapy"[MeSH] AND ("randomized controlled trial"[pt] OR "meta-analysis"[pt])',
            '"cognitive behavioral therapy"[Title/Abstract] AND ("randomized controlled trial"[pt] OR "meta-analysis"[pt])',
            '"dialectical behavior therapy"[Title/Abstract]',
            '"parent training"[Title/Abstract] AND ("child"[MeSH] OR "adolescent"[MeSH])',
            '"family therapy"[MeSH] AND ("randomized controlled trial"[pt] OR "clinical trial"[pt])',
            '"mindfulness"[Title/Abstract] AND ("mental health"[Title/Abstract] OR "depression"[Title/Abstract] OR "anxiety"[Title/Abstract]) AND ("randomized controlled trial"[pt] OR "meta-analysis"[pt])',
            '"trauma-focused"[Title/Abstract] AND ("child"[MeSH] OR "adolescent"[MeSH])',
        ],
        "max_articles": 12,
        "podcast_prompt": (
            "\u05e6\u05d5\u05e8 \u05d3\u05d9\u05d5\u05df \u05de\u05e2\u05de\u05d9\u05e7 \u05e2\u05dc \u05d4\u05de\u05de\u05e6\u05d0\u05d9\u05dd \u05d4\u05d7\u05e9\u05d5\u05d1\u05d9\u05dd \u05d1\u05d9\u05d5\u05ea\u05e8 \u05d4\u05e9\u05d1\u05d5\u05e2 \u05d1\u05e4\u05e1\u05d9\u05db\u05d5\u05ea\u05e8\u05e4\u05d9\u05d4 \u05d5\u05d4\u05ea\u05e2\u05e8\u05d1\u05d5\u05d9\u05d5\u05ea. "
            "\u05db\u05dc\u05d5\u05dc \u05d4\u05ea\u05e2\u05e8\u05d1\u05d5\u05d9\u05d5\u05ea \u05dc\u05d9\u05dc\u05d3\u05d9\u05dd \u05d5\u05de\u05d1\u05d5\u05d2\u05e8\u05d9\u05dd. \u05d3\u05d2\u05e9 \u05e2\u05dc \u05d9\u05d9\u05e9\u05d5\u05dd \u05e7\u05dc\u05d9\u05e0\u05d9 \u05d5\u05e2\u05d3\u05d5\u05d9\u05d5\u05ea \u05d0\u05de\u05e4\u05d9\u05e8\u05d9\u05d5\u05ea."
        ),
    },
]


# ── Step 1: PubMed Search ──────────────────────────────────────────────────────
def _esearch(query: str, retmax: int = 8) -> list[str]:
    """Run one esearch query. Returns list of PMIDs. Sleeps 0.4s after."""
    try:
        r = requests.get(PUBMED_BASE + "esearch.fcgi", params={
            "db": "pubmed", "term": query,
            "reldate": 8, "datetype": "edat",
            "retmax": retmax, "retmode": "json", "sort": "relevance",
        }, timeout=30)
        r.raise_for_status()
        return r.json().get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        print(f"    Warning: esearch error: {e}")
        return []
    finally:
        time.sleep(0.4)


def _esummary(pmids: list[str], topic_label: str) -> list[dict]:
    """Fetch esummary for PMIDs. Returns list of article dicts."""
    if not pmids:
        return []
    try:
        r = requests.get(PUBMED_BASE + "esummary.fcgi", params={
            "db": "pubmed", "id": ",".join(pmids), "retmode": "json",
        }, timeout=30)
        r.raise_for_status()
        result = r.json().get("result", {})
    except Exception as e:
        print(f"  ERROR esummary: {e}")
        return []

    articles = []
    for pmid in pmids:
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
            "pmid":          pmid,
            "title":         doc.get("title", "").rstrip("."),
            "journal":       doc.get("source", ""),
            "authors":       author_str,
            "pub_date":      doc.get("pubdate", ""),
            "url":           f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "topic":         topic_label,
            "abstract":      "",
            "impact_factor": 0.0,
        })
    return articles


def search_topic(topic: dict) -> list[dict]:
    """Search PubMed for one topic.
    Journal-specific queries run first -> top journals are always represented."""
    label = topic["label_en"]
    print(f"\n[{label}]")

    seen: dict[str, bool] = {}   # pmid -> True, insertion-ordered

    # 1. Journal-targeted searches (high priority)
    for journal in topic.get("journals", []):
        ids = _esearch(f'"{journal}"[Journal]', retmax=6)
        new = [p for p in ids if p not in seen]
        for p in new:
            seen[p] = True
        if new:
            print(f"  {journal}: {len(new)} article(s)")

    # 2. Broad MeSH/keyword searches (supplement)
    for query in topic.get("broad", []):
        ids = _esearch(query, retmax=8)
        for p in ids:
            if p not in seen:
                seen[p] = True

    all_pmids = list(seen.keys())[: topic.get("max_articles", 15)]
    articles  = _esummary(all_pmids, label)

    for a in articles:
        a["impact_factor"] = get_journal_if(a["journal"])
    articles.sort(key=lambda a: -a["impact_factor"])

    t1 = sum(1 for a in articles if a["impact_factor"] >= 15)
    t2 = sum(1 for a in articles if 5 <= a["impact_factor"] < 15)
    t3 = len(articles) - t1 - t2
    print(f"  Found {len(articles)} articles  (IF>=15: {t1} | IF 5-14: {t2} | other: {t3})")
    return articles


# -- Step 2: Fetch article text (full text via PMC when available) -------------
def _fetch_pmc_id(pmid: str) -> str | None:
    """Return PMC ID for this PubMed article, or None if not open-access."""
    try:
        r = requests.get(PUBMED_BASE + "elink.fcgi", params={
            "dbfrom": "pubmed", "db": "pmc",
            "id": pmid, "retmode": "json",
        }, timeout=15)
        r.raise_for_status()
        for ls in r.json().get("linksets", []):
            for lsdb in ls.get("linksetdbs", []):
                if lsdb.get("dbto") == "pmc":
                    links = lsdb.get("links", [])
                    if links:
                        return str(links[0])
    except Exception:
        pass
    return None


def _parse_abstract(raw_text: str) -> str:
    """Extract abstract section from PubMed efetch plain-text output."""
    lines = [ln.strip() for ln in raw_text.strip().split("\n") if ln.strip()]
    abstract_lines, in_abstract = [], False
    for line in lines:
        if "Abstract" in line[:30] or line.upper().startswith("ABSTRACT"):
            in_abstract = True
            continue
        if in_abstract and any(line.startswith(x) for x in ["PMID:", "DOI:", "Copyright", "©"]):
            break
        if in_abstract:
            abstract_lines.append(line)
    return " ".join(abstract_lines) or "(Abstract not available)"


def fetch_article_text(articles: list[dict]) -> list[dict]:
    """Fetch full text (PMC open access) or abstract for each article.
    Adds 'abstract', 'has_full_text', and 'pmc_id' keys. Modifies in-place."""
    print(f"\nFetching text for {len(articles)} articles (PMC full text when available)...")
    pmc_count = 0

    for i, article in enumerate(articles):
        pmid = article["pmid"]
        article["has_full_text"] = False
        article["pmc_id"] = None

        # Try PMC full text first
        pmc_id = _fetch_pmc_id(pmid)
        time.sleep(0.3)
        if pmc_id:
            try:
                r = requests.get(PUBMED_BASE + "efetch.fcgi", params={
                    "db": "pmc", "id": pmc_id,
                    "rettype": "full", "retmode": "text",
                }, timeout=30)
                if r.status_code == 200 and len(r.text) > 1000:
                    article["abstract"]      = r.text.strip()[:15000]
                    article["has_full_text"] = True
                    article["pmc_id"]        = pmc_id
                    pmc_count += 1
                    if (i + 1) % 10 == 0:
                        print(f"  {i+1}/{len(articles)} done  (full-text: {pmc_count})")
                    time.sleep(0.5)
                    continue
            except Exception:
                pass

        # Fall back to abstract
        try:
            r = requests.get(PUBMED_BASE + "efetch.fcgi", params={
                "db": "pubmed", "id": pmid,
                "rettype": "abstract", "retmode": "text",
            }, timeout=20)
            article["abstract"] = _parse_abstract(r.text)
        except Exception:
            article["abstract"] = "(Could not fetch abstract)"

        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(articles)} done  (full-text: {pmc_count})")
        time.sleep(1.2)

    print(f"  Done: {pmc_count}/{len(articles)} articles with PMC full text.")
    return articles

# ── Step 3a: Save articles.json (for Streamlit UI) ────────────────────────────
def save_articles_json(nb_infos: list[dict]) -> None:
    """Save all articles as articles.json for the web UI."""
    out_dir = Path("summaries") / DATE_STR
    out_dir.mkdir(parents=True, exist_ok=True)
    data = []
    for nb in nb_infos:
        topic = nb["topic"]
        for a in nb["articles"]:
            data.append({
                "pmid":          a["pmid"],
                "title":         a["title"],
                "journal":       a["journal"],
                "authors":       a["authors"],
                "pub_date":      a["pub_date"],
                "url":           a["url"],
                "impact_factor": a.get("impact_factor", 0.0),
                "abstract":      a.get("abstract", ""),
                "has_full_text": a.get("has_full_text", False),
                "pmc_id":        a.get("pmc_id"),
                "topic_id":      topic["id"],
                "topic_he":      topic["label_he"],
                "topic_en":      topic["label_en"],
            })
    out_path = out_dir / "articles.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved: {out_path}  ({len(data)} articles)")


# ── Step 3b: Create per-topic Markdown summary ─────────────────────────────────
def create_topic_summary(topic: dict, articles: list[dict]) -> str:
    """Write summaries/{DATE}/{topic_id}.md and return the path string."""
    date_range = f"{WEEK_START.strftime('%d/%m/%Y')} \u2013 {TODAY.strftime('%d/%m/%Y')}"

    t1 = sum(1 for a in articles if a.get("impact_factor", 0) >= 15)
    t2 = sum(1 for a in articles if 5 <= a.get("impact_factor", 0) < 15)
    t3 = len(articles) - t1 - t2

    lines = [
        f"# \U0001f4da {topic['label_he']}",
        f"### \u05e1\u05e7\u05d9\u05e8\u05ea \u05e1\u05e4\u05e8\u05d5\u05ea \u05e9\u05d1\u05d5\u05e2\u05d9\u05ea \u2014 {DATE_STR}",
        "",
        f"**\u05ea\u05e7\u05d5\u05e4\u05d4:** {date_range} | **\u05de\u05d0\u05de\u05e8\u05d9\u05dd:** {len(articles)} "
        f"(\u2b50 IF\u226515: {t1} | \U0001f537 IF 5-14: {t2} | \U0001f4c4 \u05d0\u05d7\u05e8: {t3})",
        "",
        "> **\u05de\u05e4\u05ea\u05d7:** \u2b50 \u05db\u05ea\u05d1 \u05e2\u05ea \u05de\u05d3\u05e8\u05d2\u05d4 \u05e8\u05d0\u05e9\u05d5\u05e0\u05d4 (IF \u2265 15) \u00b7 "
        "\U0001f537 \u05db\u05ea\u05d1 \u05e2\u05ea \u05de\u05d5\u05d1\u05d9\u05dc (IF 5\u201314) \u00b7 \U0001f4c4 \u05db\u05ea\u05d1 \u05e2\u05ea \u05de\u05d5\u05db\u05e8",
        "",
        "---",
        "",
    ]

    for a in articles:
        abstract = a.get("abstract", "")
        if len(abstract) > 500:
            abstract = abstract[:500] + "\u2026"
        if_val = a.get("impact_factor", 0)
        if if_val > 0:
            journal_str = f"{if_badge(if_val)} {a['journal']} *(IF: {if_val:.1f})*"
        else:
            journal_str = f"\U0001f4c4 {a['journal']}"
        lines += [
            f"### {a['title']}",
            f"**\u05db\u05ea\u05d1 \u05e2\u05ea:** {journal_str} | **\u05de\u05d7\u05d1\u05e8\u05d9\u05dd:** {a['authors']} | **\u05ea\u05d0\u05e8\u05d9\u05da:** {a['pub_date']}",
            "",
            abstract,
            "",
            f"\U0001f517 [\u05e7\u05d9\u05e9\u05d5\u05e8 \u05dc\u05de\u05d0\u05de\u05e8 \u05d1-PubMed]({a['url']})",
            "",
            "---",
            "",
        ]

    lines += [
        "## \U0001f4dd \u05d4\u05e2\u05e8\u05d5\u05ea",
        "- \u05de\u05d0\u05de\u05e8\u05d9\u05dd \u05e0\u05de\u05e6\u05d0\u05d5 \u05d0\u05d5\u05d8\u05d5\u05de\u05d8\u05d9\u05ea \u05d3\u05e8\u05da PubMed E-utilities API",
        "- \u05d4\u05e1\u05d9\u05db\u05d5\u05de\u05d9\u05dd \u05de\u05d1\u05d5\u05e1\u05e1\u05d9\u05dd \u05e2\u05dc \u05ea\u05e7\u05e6\u05d9\u05e8\u05d9\u05dd (Abstracts) \u05d1\u05dc\u05d1\u05d3",
        "",
        f"*\u05e0\u05d5\u05e6\u05e8 \u05d0\u05d5\u05d8\u05d5\u05de\u05d8\u05d9\u05ea \u05d1-{TODAY.strftime('%d/%m/%Y %H:%M')} UTC*",
    ]

    out_dir = Path("summaries") / DATE_STR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{topic['id']}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Saved: {out_path}")
    return str(out_path)


# ── NotebookLM helpers ─────────────────────────────────────────────────────────
def create_notebook(title: str, env: dict) -> tuple[str | None, str | None]:
    """Create a NotebookLM notebook. Returns (nb_id, nb_url) or (None, None)."""
    try:
        out = subprocess.run(
            ["notebooklm", "create", title, "--json"],
            capture_output=True, text=True, env=env, timeout=60,
        )
        raw = out.stdout.strip()
        if not raw:
            print(f"  ERROR: No output from create. stderr: {out.stderr[:200]}")
            return None, None
        nb_data = json.loads(raw)
        if nb_data.get("error"):
            print(f"  ERROR: {nb_data.get('message', nb_data)}")
            return None, None
        nb_id = (nb_data.get("notebook") or {}).get("id") or nb_data.get("id")
        if not nb_id:
            print(f"  ERROR: Unexpected create response: {raw[:200]}")
            return None, None
        return nb_id, f"https://notebooklm.google.com/notebook/{nb_id}"
    except Exception as e:
        print(f"  ERROR create_notebook: {e}")
        return None, None


def add_source(nb_id: str, summary_path: str, env: dict) -> bool:
    """Switch to notebook and upload the markdown summary as a source."""
    subprocess.run(
        ["notebooklm", "use", nb_id],
        capture_output=True, env=env, timeout=30,
    )
    result = subprocess.run(
        ["notebooklm", "source", "add", summary_path, "--json"],
        capture_output=True, text=True, env=env, timeout=120,
    )
    return result.returncode == 0


def start_podcast(nb_id: str, prompt: str, env: dict) -> str | None:
    """Switch to notebook and fire off podcast generation.
    Returns artifact_id or None. Does NOT wait for completion."""
    subprocess.run(
        ["notebooklm", "use", nb_id],
        capture_output=True, env=env, timeout=30,
    )
    try:
        out = subprocess.run([
            "notebooklm", "generate", "audio", prompt,
            "--format", "deep-dive", "--language", "he", "--json",
        ], capture_output=True, text=True, env=env, timeout=120)
        data = json.loads(out.stdout.strip())
        return data.get("task_id") or None
    except Exception as e:
        print(f"  ERROR start_podcast: {e}")
        return None


# ── Wait for all podcasts (parallel on Google's side) ─────────────────────────
def wait_for_all_podcasts(nb_infos: list[dict], env: dict, max_wait: int = 2700):
    """Poll every notebook until all started podcasts complete or time out."""
    pending = {
        nb["nb_id"]: nb
        for nb in nb_infos
        if nb.get("nb_id") and nb.get("artifact_id")
    }
    if not pending:
        print("  No podcasts to wait for.")
        return

    print(f"\nWaiting for {len(pending)} podcast(s) (parallel on Google's servers, up to {max_wait // 60} min)...")
    start = time.time()

    while pending and time.time() - start < max_wait:
        time.sleep(60)
        elapsed = int(time.time() - start)
        for nb_id in list(pending.keys()):
            nb = pending[nb_id]
            subprocess.run(
                ["notebooklm", "use", nb_id],
                capture_output=True, env=env, timeout=30,
            )
            try:
                out = subprocess.run(
                    ["notebooklm", "artifact", "list", "--json"],
                    capture_output=True, text=True, env=env, timeout=30,
                )
                artifacts = json.loads(out.stdout).get("artifacts", [])
                for a in artifacts:
                    if a.get("id") == nb["artifact_id"]:
                        status = a.get("status", "unknown")
                        label  = nb["topic"]["label_en"]
                        print(f"  [{elapsed // 60}m] {label}: {status}")
                        if status == "completed":
                            nb["podcast_ready"] = True
                            del pending[nb_id]
                        elif status in ("failed", "unknown"):
                            print(f"  ERROR: {label} podcast failed.")
                            del pending[nb_id]
            except Exception as e:
                print(f"  Warning: polling error for {nb_id}: {e}")

    if pending:
        remaining = [pending[k]["topic"]["label_en"] for k in pending]
        print(f"WARNING: Timed out waiting for: {', '.join(remaining)}")


# ── Download podcast ───────────────────────────────────────────────────────────
def download_podcast(nb_id: str, artifact_id: str, topic_id: str, env: dict) -> str | None:
    podcast_dir = Path("podcasts") / DATE_STR
    podcast_dir.mkdir(parents=True, exist_ok=True)
    path = podcast_dir / f"{topic_id}.mp3"

    subprocess.run(
        ["notebooklm", "use", nb_id],
        capture_output=True, env=env, timeout=30,
    )
    result = subprocess.run(
        ["notebooklm", "download", "audio", str(path), "-a", artifact_id],
        capture_output=True, text=True, env=env, timeout=300,
    )
    if result.returncode == 0 and path.exists() and path.stat().st_size > 0:
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"  Downloaded {topic_id}: {size_mb:.1f} MB")
        return str(path)
    print(f"  ERROR: Download failed: {result.stderr[:200]}")
    return None


# ── Commit summaries to GitHub ────────────────────────────────────────────────
def commit_summaries_to_github(env: dict):
    """Commit and push today's summaries folder to GitHub main branch."""
    repo  = env.get("GITHUB_REPOSITORY") or env.get("GH_REPO", "")
    token = env.get("GITHUB_TOKEN") or env.get("GH_TOKEN", "")
    if not repo or not token:
        print("  WARNING: GH_REPO / GH_TOKEN not set -- skipping commit")
        return

    # Set git identity so the commit is accepted
    subprocess.run(["git", "config", "user.email", "bot@weekly-review"], check=False)
    subprocess.run(["git", "config", "user.name",  "Weekly Review Bot"],  check=False)

    # Configure remote with token for authenticated push
    remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"
    subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=False)

    # Stage only today's summaries directory
    summaries_dir = f"summaries/{DATE_STR}"
    subprocess.run(["git", "add", summaries_dir], check=False)

    # Check if there's anything to commit
    status = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
    if status.returncode == 0:
        print("  No new summaries to commit.")
        return

    result = subprocess.run(
        ["git", "commit", "-m", f"\U0001f4da Weekly review {DATE_STR}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  WARNING: git commit failed: {result.stderr.strip()}")
        return

    push = subprocess.run(
        ["git", "push", "origin", "main"],
        capture_output=True, text=True,
    )
    if push.returncode == 0:
        print(f"  Summaries committed and pushed to GitHub ({summaries_dir})")
    else:
        print(f"  WARNING: git push failed: {push.stderr.strip()}")


# ── Upload to GitHub Release ───────────────────────────────────────────────────
def upload_to_github_release(podcast_path: str, topic: dict, env: dict) -> str | None:
    tag    = f"weekly-{DATE_STR}-{topic['id']}"
    # Support both GitHub Actions (GITHUB_REPOSITORY) and Cloud Run (GH_REPO)
    repo   = env.get("GITHUB_REPOSITORY") or env.get("GH_REPO", "")
    server = env.get("GITHUB_SERVER_URL", "https://github.com")

    if not repo:
        print("  WARNING: GITHUB_REPOSITORY not set")
        return None

    subprocess.run([
        "gh", "release", "create", tag, podcast_path,
        "--title", f"\U0001f4da {topic['label_he']} \u2014 {DATE_STR}",
        "--notes", f"{topic['label_en']} weekly literature review {DATE_STR}\n\n*Generated automatically*",
        "--repo", repo,
    ], capture_output=True, text=True, env=env, timeout=180)

    view = subprocess.run([
        "gh", "release", "view", tag,
        "--json", "assets", "--jq", ".assets[0].browserDownloadUrl",
        "--repo", repo,
    ], capture_output=True, text=True, env=env, timeout=30)

    url = view.stdout.strip()
    if url:
        return url
    filename = Path(podcast_path).name
    return f"{server}/{repo}/releases/download/{tag}/{filename}"


# ── Push notification ──────────────────────────────────────────────────────────
def send_notification(nb_infos: list[dict], env: dict):
    ntfy_topic = env.get("NTFY_TOPIC")
    if not ntfy_topic:
        print("WARNING: NTFY_TOPIC not set -- skipping notification")
        return

    print("\nSending push notification...")

    total_articles = sum(len(nb["articles"]) for nb in nb_infos)
    ready_podcasts = sum(1 for nb in nb_infos if nb.get("podcast_url"))

    body_lines = [
        f"\u05e0\u05de\u05e6\u05d0\u05d5 {total_articles} \u05de\u05d0\u05de\u05e8\u05d9\u05dd \u05d7\u05d3\u05e9\u05d9\u05dd \u05d1-{len(nb_infos)} \u05ea\u05d7\u05d5\u05de\u05d9\u05dd:"
    ]
    for nb in nb_infos:
        icon = "\U0001f399\ufe0f" if nb.get("podcast_url") else ("\U0001f4d3" if nb.get("nb_url") else "\U0001f4cb")
        body_lines.append(f"  {icon} {nb['topic']['label_he']}: {len(nb['articles'])} \u05de\u05d0\u05de\u05e8\u05d9\u05dd")
    if ready_podcasts:
        body_lines.append(f"\n\u2705 {ready_podcasts}/{len(nb_infos)} \u05e4\u05d5\u05d3\u05e7\u05d0\u05e1\u05d8\u05d9\u05dd \u05de\u05d5\u05db\u05e0\u05d9\u05dd.")

    # ntfy supports max 3 action buttons
    actions = []
    for nb in nb_infos:
        if nb.get("podcast_url") and len(actions) < 3:
            actions.append({
                "action": "view",
                "label":  f"\U0001f399\ufe0f {nb['topic']['label_he']}",
                "url":    nb["podcast_url"],
            })

    repo   = env.get("GITHUB_REPOSITORY") or env.get("GH_REPO", "")
    server = env.get("GITHUB_SERVER_URL", "https://github.com")
    if repo and len(actions) < 3:
        actions.append({
            "action": "view",
            "label":  "\U0001f4cb \u05db\u05dc \u05d4\u05e1\u05d9\u05db\u05d5\u05de\u05d9\u05dd",
            "url":    f"{server}/{repo}/tree/main/summaries/{DATE_STR}",
        })

    # Add Streamlit UI link
    ui_url = env.get("UI_URL", "")
    if ui_url and len(actions) < 3:
        actions.insert(0, {"action": "view", "label": "Streamlit UI", "url": ui_url})

    payload = {
        "topic":    ntfy_topic,
        "title":    f"\U0001f4da \u05e1\u05e7\u05d9\u05e8\u05ea \u05e1\u05e4\u05e8\u05d5\u05ea \u05e9\u05d1\u05d5\u05e2\u05d9\u05ea \u2014 {DATE_STR}",
        "message":  "\n".join(body_lines),
        "tags":     ["books", "white_check_mark"],
        "priority": 3,
        "actions":  actions[:3],
    }

    for attempt in range(5):
        try:
            r = requests.post("https://ntfy.sh", json=payload, timeout=15)
            print(f"  Notification sent (status {r.status_code})")
            if r.status_code == 429:
                wait = 90 * (attempt + 1)   # 90s, 180s, 270s, 360s, 450s
                print(f"  Rate limited (attempt {attempt+1}/5) -- retrying in {wait}s...")
                time.sleep(wait)
                continue
            break
        except Exception as e:
            print(f"  ERROR: Notification failed: {e}")
            if attempt < 4:
                time.sleep(30)
                continue
            break


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    sep = "=" * 65
    print(f"\n{sep}")
    print(f"\U0001f4da Weekly Psychiatry Literature Review -- {DATE_STR}")
    print(f"   {len(TOPICS)} topics, journal-targeted searches + broad MeSH")
    print(f"{sep}\n")

    env = os.environ.copy()

    # Cloud Run: NOTEBOOKLM_AUTH_JSON env var → write to local file
    auth_json = env.get("NOTEBOOKLM_AUTH_JSON", "")
    if auth_json:
        storage_path = Path.home() / ".notebooklm" / "storage_state.json"
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_text(auth_json, encoding="utf-8")

    # Local run: detect existing session file even without the env var
    local_session = Path.home() / ".notebooklm" / "storage_state.json"
    has_notebooklm = bool(auth_json) or local_session.exists()

    # ── Auth pre-check: verify session is alive before doing any work ─────────
    if has_notebooklm:
        print("Verifying NotebookLM session...")
        result = subprocess.run(
            ["notebooklm", "list", "--json"],
            capture_output=True, text=True, timeout=60,
        )
        combined = (result.stdout + result.stderr).lower()
        if any(w in combined for w in ["auth", "signin", "login", "expired", "redirect"]):
            print("WARNING: NotebookLM session is EXPIRED -- NotebookLM steps will be skipped.")
            ntfy_topic = env.get("NTFY_TOPIC", "")
            if ntfy_topic:
                try:
                    requests.post("https://ntfy.sh", json={
                        "topic":    ntfy_topic,
                        "title":    "Auth expired -- action required",
                        "message":  "NotebookLM session expired. Run: notebooklm login",
                        "tags":     ["warning"],
                        "priority": 4,
                    }, timeout=15)
                except Exception:
                    pass
            has_notebooklm = False
        else:
            print("Session is alive.")

    # ── Phase 1: Search + Summaries ───────────────────────────────────────────
    nb_infos: list[dict] = []
    all_articles: list[dict] = []

    print("\U0001f50d Searching PubMed for all topics...")
    for topic in TOPICS:
        articles = search_topic(topic)
        if not articles:
            print(f"  WARNING: No articles for {topic['label_en']}, skipping.")
            continue
        all_articles.extend(articles)
        nb_infos.append({
            "topic":         topic,
            "articles":      articles,
            "summary_path":  None,
            "nb_id":         None,
            "nb_url":        None,
            "artifact_id":   None,
            "podcast_ready": False,
            "podcast_path":  None,
            "podcast_url":   None,
        })

    if not nb_infos:
        print("ERROR: No articles found in any topic!")
        send_notification([], env)
        sys.exit(1)

    # Fetch text for ALL articles in one pass (PMC full text when available)
    fetch_article_text(all_articles)

    # Save articles.json for web UI, then per-topic summaries
    save_articles_json(nb_infos)
    print("\n\U0001f4dd Creating topic summaries...")
    for nb in nb_infos:
        nb["summary_path"] = create_topic_summary(nb["topic"], nb["articles"])

    # Commit summaries to GitHub regardless of NotebookLM status
    print("\n\U0001f4e4 Committing summaries to GitHub...")
    commit_summaries_to_github(env)

    if not has_notebooklm:
        print("\nWARNING: No NotebookLM session found -- skipping notebooks & podcasts")
        send_notification(nb_infos, env)
        return

    # ── Phase 2: Create notebooks ─────────────────────────────────────────────
    print(f"\n\U0001f5d2\ufe0f  Creating {len(nb_infos)} notebooks...")
    for nb in nb_infos:
        title = f"{nb['topic']['label_he']} \u2014 {DATE_STR}"
        print(f"  Creating: {title}")
        nb_id, nb_url = create_notebook(title, env)
        nb["nb_id"]  = nb_id
        nb["nb_url"] = nb_url
        print(f"  {'OK' if nb_id else 'FAILED'}: {nb_id or 'n/a'}")

    # ── Phase 3: Add sources ──────────────────────────────────────────────────
    print("\n\U0001f4ce Adding sources to all notebooks...")
    for nb in nb_infos:
        if nb["nb_id"]:
            ok = add_source(nb["nb_id"], nb["summary_path"], env)
            print(f"  {'OK' if ok else 'FAILED'}: {nb['topic']['label_en']}")

    # Wait for indexing (markdown files index in < 1 min; 2 min is safe)
    print("\nWaiting 2 min for sources to be indexed...")
    time.sleep(120)

    # ── Phase 4: Start all podcast generations ────────────────────────────────
    print(f"\n\U0001f3d9\ufe0f  Starting {len(nb_infos)} podcast generation(s)...")
    for nb in nb_infos:
        if nb["nb_id"]:
            artifact_id = start_podcast(nb["nb_id"], nb["topic"]["podcast_prompt"], env)
            nb["artifact_id"] = artifact_id
            status = f"artifact {artifact_id}" if artifact_id else "FAILED to start"
            print(f"  {'OK' if artifact_id else 'FAIL'}: {nb['topic']['label_en']} -> {status}")
            time.sleep(10)   # short pause to avoid rate-limiting

    # ── Phase 5: Wait for all podcasts (parallel on Google's side) ────────────
    wait_for_all_podcasts(nb_infos, env, max_wait=2700)

    # ── Phase 6: Download + Upload ────────────────────────────────────────────
    print("\n\u2b07\ufe0f  Downloading & uploading completed podcasts...")
    for nb in nb_infos:
        if nb.get("podcast_ready") and nb.get("nb_id") and nb.get("artifact_id"):
            path = download_podcast(nb["nb_id"], nb["artifact_id"], nb["topic"]["id"], env)
            nb["podcast_path"] = path
            if path:
                print(f"  Uploading {nb['topic']['label_en']}...")
                url = upload_to_github_release(path, nb["topic"], env)
                nb["podcast_url"] = url
                print(f"  -> {url}")

    # ── Phase 7: Notify ───────────────────────────────────────────────────────
    send_notification(nb_infos, env)

    # ── Final summary ─────────────────────────────────────────────────────────
    print(f"\n{sep}")
    print("All done!")
    for nb in nb_infos:
        print(f"\n  {nb['topic']['label_he']}")
        print(f"    Articles : {len(nb['articles'])}")
        print(f"    Notebook : {nb.get('nb_url') or '--'}")
        print(f"    Podcast  : {nb.get('podcast_url') or '--'}")
    print(f"\n{sep}\n")


if __name__ == "__main__":
    main()
