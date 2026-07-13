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
import re
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
    "lancet child adolesc health":                              45.7,
    "nature medicine":                                          87.2,
    "nature":                                                   69.5,
    "science":                                                  67.2,
    "world psychiatry":                                         73.3,
    "bmj":                                                     105.7,
    "nature neuroscience":                                      25.0,
    "nat neurosci":                                             25.0,
    "jama pediatrics":                                          27.6,
    "jama pediatr":                                             27.6,
    "american journal of psychiatry":                           18.1,
    "am j psychiatry":                                          18.1,
    "annals of internal medicine":                              39.2,
    "psychotherapy and psychosomatics":                         15.0,
    "psychother psychosom":                                     15.0,
    "brain":                                                    14.5,
    # Tier 2
    "molecular psychiatry":                                     13.4,
    "mol psychiatry":                                           13.4,
    "clinical psychology review":                               12.0,
    "clin psychol rev":                                         12.0,
    "psychological review":                                     12.0,
    "psychol rev":                                              12.0,
    "biological psychiatry":                                    12.8,
    "biol psychiatry":                                          12.8,
    "jaacap":                                                   10.2,
    "journal of the american academy of child and adolescent psychiatry": 10.2,
    "j am acad child adolesc psychiatry":                       10.2,
    "neuropsychopharmacology":                                   8.0,
    "pediatrics":                                                8.0,
    "journal of neuroscience":                                   6.7,
    "j neurosci":                                                6.7,
    # ECNP's "Neuroscience Applied" — launched 2022, IF not yet indexed by
    # JCR. Placeholder value of 3.0 puts it in tier 3 so it doesn't crowd
    # out the established journals when sorting; the user can adjust once
    # an official IF lands.
    "neuroscience applied":                                      3.0,
    "neurosci appl":                                             3.0,
    "schizophrenia bulletin":                                    7.4,
    "journal of child psychology and psychiatry":                7.2,
    "j child psychol psychiatry":                                7.2,
    "acta psychiatrica scandinavica":                            6.7,
    "psychological medicine":                                    6.0,
    "psychol med":                                               6.0,
    "european child and adolescent psychiatry":                  6.0,
    "eur child adolesc psychiatry":                              6.0,
    "depression and anxiety":                                    6.0,
    "european neuropsychopharmacology":                          5.5,
    "behavioral and brain sciences":                            20.0,
    "behav brain sci":                                          20.0,
    "psychological science":                                     5.5,
    "psychol sci":                                               5.5,
    "journal of experimental psychology general":                5.5,
    "j exp psychol gen":                                         5.5,
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
    "child adolesc ment health":                                  3.0,
    "journal of developmental and behavioral pediatrics":         3.0,
    "j child adolesc psychopharmacol":                           3.5,
    "journal of child and adolescent psychopharmacology":        3.5,
    "dev med child neurol":                                      4.5,
    "developmental medicine and child neurology":                4.5,
    "dev psychopathol":                                          5.8,
    "development and psychopathology":                           5.8,
    "child dev":                                                 5.4,
    "child development":                                         5.4,
    "developmental psychology":                                  5.0,
    "dev psychol":                                               5.0,
    "developmental science":                                     4.4,
    "dev sci":                                                   4.4,
    "infant mental health journal":                              2.5,
    "infant ment health j":                                      2.5,
    "neuron":                                                   17.2,
    "cerebral cortex":                                           4.9,
    "journal of cognitive neuroscience":                         4.4,
    "j cogn neurosci":                                           4.4,
    "cognitive psychology":                                      3.5,
    "cogn psychol":                                              3.5,
    "cognition":                                                 3.5,
    "journal of experimental child psychology":                  3.5,
    "j exp child psychol":                                       3.5,
    "behavioral neuroscience":                                   3.0,
    "behav neurosci":                                            3.0,
    "journal of applied behavior analysis":                      2.5,
    "j appl behav anal":                                         2.5,
    "international journal of psychoanalysis":                   1.5,
    "int j psychoanal":                                          1.5,
    "psychoanalytic psychology":                                 1.7,
    "attachment and human development":                          3.5,
    "attach hum dev":                                            3.5,
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


# \u2500\u2500 Journal abbreviation \u2192 full name \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
# PubMed returns the abbreviated journal title (e.g. "J Child Psychol
# Psychiatry"). NotebookLM's hosts often read the abbreviation aloud, which
# sounds cryptic (" jay-child-sigh-coal"). We render the FULL name in the
# markdown source so the hosts have it, and a prompt directive tells them to
# say the full name. Keyed by the lower-cased abbreviation PubMed emits.
JOURNAL_FULL_NAME: dict[str, str] = {
    "j am acad child adolesc psychiatry":
        "Journal of the American Academy of Child and Adolescent Psychiatry",
    "j child psychol psychiatry":
        "Journal of Child Psychology and Psychiatry",
    "eur child adolesc psychiatry":
        "European Child & Adolescent Psychiatry",
    "child adolesc ment health":
        "Child and Adolescent Mental Health",
    "lancet child adolesc health":
        "The Lancet Child & Adolescent Health",
    "jama pediatr":            "JAMA Pediatrics",
    "jama psychiatry":         "JAMA Psychiatry",
    "am j psychiatry":         "The American Journal of Psychiatry",
    "lancet psychiatry":       "The Lancet Psychiatry",
    "world psychiatry":        "World Psychiatry",
    "acta psychiatr scand":    "Acta Psychiatrica Scandinavica",
    "mol psychiatry":          "Molecular Psychiatry",
    "biol psychiatry":         "Biological Psychiatry",
    "neuropsychopharmacology": "Neuropsychopharmacology",
    "n engl j med":            "The New England Journal of Medicine",
    "nat neurosci":            "Nature Neuroscience",
    "j neurosci":              "The Journal of Neuroscience",
    "neurosci appl":           "Neuroscience Applied",
    "child dev":               "Child Development",
    "dev psychopathol":        "Development and Psychopathology",
    "dev psychol":             "Developmental Psychology",
    "dev sci":                 "Developmental Science",
    "infant ment health j":    "Infant Mental Health Journal",
    "j abnorm child psychol":  "Journal of Abnormal Child Psychology",
    "psychother psychosom":    "Psychotherapy and Psychosomatics",
    "clin psychol rev":        "Clinical Psychology Review",
    "behav res ther":          "Behaviour Research and Therapy",
    "j consult clin psychol":  "Journal of Consulting and Clinical Psychology",
    "int j psychoanal":        "The International Journal of Psychoanalysis",
    "behav brain sci":         "Behavioral and Brain Sciences",
    "psychol sci":             "Psychological Science",
    "j exp psychol gen":       "Journal of Experimental Psychology: General",
    "behav neurosci":          "Behavioral Neuroscience",
    "psychol rev":             "Psychological Review",
    "j cogn neurosci":         "Journal of Cognitive Neuroscience",
    "cogn psychol":            "Cognitive Psychology",
    "j exp child psychol":     "Journal of Experimental Child Psychology",
}


def journal_full_name(abbrev: str) -> str:
    """Return the full journal name for a PubMed abbreviation, or the
    abbreviation unchanged if we don't have a mapping."""
    return JOURNAL_FULL_NAME.get(abbrev.lower().strip(), abbrev)


# ── Topic Definitions ──────────────────────────────────────────────────────────
# Each topic:
#   journals  -- searched directly by journal name (all recent articles)
#   broad     -- PubMed queries used when content filtering is needed
#   max_articles, podcast_prompt
#
# CLUSTER OVERVIEW (10 topics):
#  1. child_adolescent_core        — JAACAP, JCPP, ECAP, CAMH (ALL articles)
#  2. child_adolescent_highimpact  — JAMA Psych/Pediatr, Lancet Psych/Child, NEJM (child-filtered)
#  3. general_psychiatry_clinical  — World Psych, JAMA Psych, AJP, Lancet Psych (NOT child)
#  4. general_psychiatry_bio       — Mol Psychiatry, Biol Psychiatry, NEJM (NOT child)
#  5. child_development            — Dev Psychopathol, Child Dev, Dev Psychol, Dev Sci, IMHJ
#  6. neuroscience                 — Nat Neurosci, Neuron, Biol Psychiatry, Brain, NPP, J Neurosci
#  7. psychotherapy                — Psychother Psychosom, Clin Psychol Rev, BRT, JCCP, Int J Psychoanal
#  8. behavioral_sciences          — Behav Brain Sci, Psychol Sci, J Exp Psychol Gen, Behav Neurosci
#  9. cognition                    — Psychol Rev, J Cogn Neurosci, Cogn Psychol, Cognition, J Exp Child Psychol
# 10. child_adolescent_misc        — broad MeSH child/adolescent psych, NOT from clusters 1+2
TOPICS = [
    {
        # ── CLUSTER 1 ────────────────────────────────────────────────────────────────────
        # Core child & adolescent psychiatry journals — ALL new articles
        "id":       "child_adolescent_core",
        "label_en": "Child & Adolescent Psychiatry — Core",
        "label_he": "ליבה — פסיכיאטריית ילד ומתבגר",
        "journals": [
            "J Am Acad Child Adolesc Psychiatry",   # JAACAP — flagship
            "J Child Psychol Psychiatry",            # JCPP
            "Eur Child Adolesc Psychiatry",          # ECAP
            "Child Adolesc Mental Health",           # CAMH
        ],
        "broad": [],
        "max_articles": 40,
        "podcast_prompt": (
            "Produce a comprehensive discussion of this week's key findings in child "
            "and adolescent psychiatry. Cover each paper according to its own focus — "
            "methods, findings, clinical implications, and what a child/adolescent "
            "psychiatry resident should take from it. "
            "Generate the podcast entirely in Hebrew."
        ),
    },
    {
        # ── CLUSTER 2 ────────────────────────────────────────────────────────────────────
        # High-impact journals filtered for child / adolescent content
        "id":       "child_adolescent_highimpact",
        "label_en": "Child & Adolescent Psychiatry — High Impact",
        "label_he": "השפעה גבוהה — ילד ומתבגר",
        "journals": [
            "Lancet Child Adolesc Health",           # IF~45 — dedicated child journal
            "JAMA Pediatr",                          # IF~27 — filtered to mental-health content
        ],
        # Per-journal filter — applied to each journal query so we keep ONLY
        # mental-health / psychiatry-relevant articles from generalist pediatric
        # and child-health journals (JAMA Pediatr publishes plenty of non-MH
        # pediatrics; Lancet Child Adolesc Health publishes oncology / ID etc.).
        "journal_filter": (
            '("mental health"[Title/Abstract] OR "psychiat*"[Title/Abstract] '
            'OR "psychopathology"[Title/Abstract] OR "ADHD"[Title/Abstract] '
            'OR "attention-deficit"[Title/Abstract] OR "autism"[Title/Abstract] '
            'OR "anxiety"[Title/Abstract] OR "depress*"[Title/Abstract] '
            'OR "behavior*"[Title/Abstract] OR "suicid*"[Title/Abstract] '
            'OR "self-harm"[Title/Abstract] OR "eating disorder*"[Title/Abstract] '
            'OR "substance use"[Title/Abstract] OR "trauma*"[Title/Abstract] '
            'OR "neurodevelopmental"[Title/Abstract] OR "tic*"[Title/Abstract] '
            'OR "OCD"[Title/Abstract] OR "obsessive"[Title/Abstract] '
            'OR "psychosis"[Title/Abstract] OR "schizophrenia"[Title/Abstract])'
        ),
        "broad": [
            '"JAMA Psychiatry"[Journal] AND ("child"[MeSH] OR "adolescent"[MeSH] OR "youth"[Title/Abstract] OR "pediatric"[Title/Abstract])',
            '"Lancet Psychiatry"[Journal] AND ("child"[MeSH] OR "adolescent"[MeSH] OR "youth"[Title/Abstract])',
            '"Am J Psychiatry"[Journal] AND ("child"[MeSH] OR "adolescent"[MeSH] OR "pediatric"[Title/Abstract])',
            '"World Psychiatry"[Journal] AND ("child"[MeSH] OR "adolescent"[MeSH] OR "youth"[Title/Abstract])',
            '"N Engl J Med"[Journal] AND ("child psychiatry"[Title/Abstract] OR "adolescent psychiatry"[Title/Abstract] OR "autism"[Title/Abstract] OR "ADHD"[Title/Abstract] OR "child mental health"[Title/Abstract])',
            '"JAMA"[Journal] AND ("child"[MeSH] OR "adolescent"[MeSH]) AND ("mental health"[Title/Abstract] OR "psychiatry"[Title/Abstract] OR "autism"[Title/Abstract] OR "ADHD"[Title/Abstract])',
        ],
        "max_articles": 20,
        "podcast_prompt": (
            "Discuss the high-impact child/adolescent papers of the week from leading "
            "medical journals. For each: significance, potential practice changes, "
            "and relevance to child and adolescent psychiatry. "
            "Generate the podcast entirely in Hebrew."
        ),
    },
    {
        # ── CLUSTER 3 ────────────────────────────────────────────────────────────────────
        # General clinical psychiatry — adult-focused (excludes child/adolescent)
        "id":       "general_psychiatry_clinical",
        "label_en": "General Psychiatry — Clinical",
        "label_he": "פסיכיאטריה כללית — קלינית",
        "journals": [
            "World Psychiatry",
            "Am J Psychiatry",
            "Acta Psychiatr Scand",
        ],
        "broad": [
            '"JAMA Psychiatry"[Journal] NOT ("child"[MeSH] OR "adolescent"[MeSH])',
            '"Lancet Psychiatry"[Journal] NOT ("child"[MeSH] OR "adolescent"[MeSH])',
            '("schizophrenia"[MeSH] OR "bipolar disorder"[MeSH]) AND ("randomized controlled trial"[pt] OR "meta-analysis"[pt])',
            '"depressive disorder, major"[MeSH] AND ("randomized controlled trial"[pt] OR "meta-analysis"[pt])',
            '"suicide"[MeSH] AND ("prevention"[Title/Abstract] OR "risk factors"[Title/Abstract])',
            '"psychosis"[Title/Abstract] AND "first episode"[Title/Abstract]',
            '"borderline personality disorder"[MeSH] AND ("treatment"[Title/Abstract] OR "therapy"[Title/Abstract])',
        ],
        # Raised to 22 (was 12): pulls from pure top-tier journals (World
        # Psych, AJP, Acta) + curated MeSH, so more headroom is genuine
        # signal. With SPLIT_THRESHOLD=18 a crowded week splits into 2 parts.
        "max_articles": 22,
        "podcast_prompt": (
            "Review this week's key clinical findings in general (adult) psychiatry. "
            "Discuss each paper on its own terms — methods, findings, and clinical "
            "implications for the population the study addresses. "
            "Do NOT filter or shorten papers because they focus on adults. "
            "Where a finding has a clear bearing on child or adolescent psychiatry, "
            "add a brief note — but only when the connection arises from the paper itself. "
            "Generate the podcast entirely in Hebrew."
        ),
    },
    {
        # ── CLUSTER 4 ────────────────────────────────────────────────────────────────────
        # Biological psychiatry — genetics, neurobiology, pharmacology
        "id":       "general_psychiatry_bio",
        "label_en": "Biological Psychiatry",
        "label_he": "פסיכיאטריה ביולוגית",
        "journals": [
            "Mol Psychiatry",
            "Biol Psychiatry",
            "Neuropsychopharmacology",
        ],
        "broad": [
            '"N Engl J Med"[Journal] AND ("psychiatry"[Title/Abstract] OR "mental health"[Title/Abstract] OR "schizophrenia"[Title/Abstract] OR "depression"[Title/Abstract] OR "bipolar"[Title/Abstract]) NOT ("child"[MeSH] OR "adolescent"[MeSH])',
            '"genetics"[MeSH] AND ("psychiatry"[Title/Abstract] OR "psychiatric disorders"[Title/Abstract]) AND ("genome-wide"[Title/Abstract] OR "GWAS"[Title/Abstract])',
            '"antidepressants"[MeSH] AND ("randomized controlled trial"[pt] OR "meta-analysis"[pt])',
            '"antipsychotic agents"[MeSH] AND ("randomized controlled trial"[pt] OR "meta-analysis"[pt])',
        ],
        # Raised to 20 (was 10) — feeds the psychiatry channel; splits when crowded.
        "max_articles": 20,
        "podcast_prompt": (
            "Review this week's key biological and psychopharmacological research. "
            "Discuss mechanisms, genetics, and pharmacological findings in the "
            "original context of each study. Cover adult-focused findings fully. "
            "Add notes on relevance to child/adolescent psychiatry only when the "
            "study itself supports such a link. "
            "Generate the podcast entirely in Hebrew."
        ),
    },
    {
        # ── CLUSTER 5 ────────────────────────────────────────────────────────────────────
        # Child development — developmental science, early childhood, parenting
        "id":       "child_development",
        "label_en": "Child Development",
        "label_he": "התפתחות הילד",
        "journals": [
            "Child Dev",
            "Dev Psychopathol",
            "Dev Psychol",
            "Dev Sci",
            "Infant Ment Health J",
            "J Abnorm Child Psychol",
        ],
        # Filter developmental journals (Dev Psychol, Dev Sci, Child Dev publish
        # plenty of non-clinical developmental research) for content relevant to
        # child & adolescent psychiatry. Dev Psychopathol, IMHJ, J Abnorm Child
        # Psychol are inherently relevant — the filter just doesn't shrink them.
        "journal_filter": (
            '("psychiat*"[Title/Abstract] OR "mental health"[Title/Abstract] '
            'OR "psychopathology"[Title/Abstract] OR "disorder*"[Title/Abstract] '
            'OR "ADHD"[Title/Abstract] OR "autism"[Title/Abstract] '
            'OR "anxiety"[Title/Abstract] OR "depress*"[Title/Abstract] '
            'OR "internalizing"[Title/Abstract] OR "externalizing"[Title/Abstract] '
            'OR "trauma*"[Title/Abstract] OR "attachment"[Title/Abstract] '
            'OR "abuse"[Title/Abstract] OR "neglect"[Title/Abstract] '
            'OR "adverse"[Title/Abstract] OR "behavior problems"[Title/Abstract] '
            'OR "self-regulation"[Title/Abstract] OR "emotion regulation"[Title/Abstract] '
            'OR "suicid*"[Title/Abstract] OR "self-harm"[Title/Abstract])'
        ),
        "broad": [
            '"adverse childhood experiences"[Title/Abstract]',
            '"parenting"[MeSH] AND ("child behavior"[MeSH] OR "mental health"[Title/Abstract])',
            '"attachment behavior"[MeSH]',
            '"early intervention"[MeSH] AND ("child"[MeSH] OR "infant"[MeSH])',
            '"social-emotional development"[Title/Abstract]',
            '"trauma"[Title/Abstract] AND ("child"[MeSH] OR "infant"[MeSH])',
        ],
        "max_articles": 10,
        "podcast_prompt": (
            "Review this week's key research in child development. Cover developmental "
            "science, attachment, early intervention, and the implications for "
            "understanding normative and pathological development. "
            "Generate the podcast entirely in Hebrew."
        ),
    },
    {
        # ── CLUSTER 6 ────────────────────────────────────────────────────────────────────
        # Neuroscience — brain, circuits, development; psychiatry-relevant
        "id":       "neuroscience",
        "label_en": "Neuroscience",
        "label_he": "מדעי המוח",
        "journals": [
            "Nat Neurosci",
            "Neuron",
            "Brain",
            "J Neurosci",
            # ECNP's official open-access journal — translational neuroscience
            # with strong psychiatry focus (added per user request, 2026-05-31).
            "Neuroscience Applied",
        ],
        # No journal_filter — goal is a general overview of what is happening
        # in top neuroscience journals, regardless of direct psychiatric link.
        "broad": [],
        # Raised to 20 (was 12) — pure top-journal pull; splits when crowded.
        "max_articles": 20,
        "podcast_prompt": (
            "Review this week's neuroscience findings from the top journals — "
            "Nature Neuroscience, Neuron, Brain, J Neurosci. The goal is a "
            "GENERAL OVERVIEW of what is happening in neuroscience this week. "
            "Cover the most important and recent papers regardless of direct "
            "psychiatric relevance. Discuss each paper on its own terms: "
            "the scientific question, the methods, the findings, and the "
            "significance within neuroscience. "
            "Where a finding has a clear bearing on child or adolescent psychiatry "
            "(neural development, circuits underlying ADHD / autism / mood / "
            "psychosis, pharmacological mechanisms, stress neurobiology), add a "
            "brief connecting note for the listener — but do NOT let perceived "
            "clinical relevance drive paper selection or how much time you spend. "
            "Treat each paper according to its own merits. "
            "Generate the podcast entirely in Hebrew."
        ),
    },
    {
        # ── CLUSTER 7 ────────────────────────────────────────────────────────────────────
        # Psychotherapy & interventions — children and adults, evidence-based
        "id":       "psychotherapy",
        "label_en": "Psychotherapy & Interventions",
        "label_he": "פסיכותרפיה והתערבויות",
        "journals": [
            "Psychother Psychosom",
            "Clin Psychol Rev",
            "Behav Res Ther",
            "J Consult Clin Psychol",
        ],
        # No journal_filter — goal is a general overview of psychotherapy
        # research, both for children and adults.
        "broad": [
            '"Int J Psychoanal"[Journal] OR "International Journal of Psychoanalysis"[Journal]',
            '"psychotherapy"[MeSH] AND ("randomized controlled trial"[pt] OR "meta-analysis"[pt])',
            '"cognitive behavioral therapy"[Title/Abstract] AND ("randomized controlled trial"[pt] OR "meta-analysis"[pt])',
            '"dialectical behavior therapy"[Title/Abstract]',
            '"psychodynamic"[Title/Abstract] AND ("randomized controlled trial"[pt] OR "meta-analysis"[pt])',
        ],
        # Raised to 20 (was 12) — main feeder of the therapy channel; splits when crowded.
        "max_articles": 20,
        "podcast_prompt": (
            "Review this week's key findings in psychotherapy research from the "
            "leading journals (Psychother Psychosom, Clin Psychol Rev, Behav Res "
            "Ther, J Consult Clin Psychol, Int J Psychoanal). The goal is a "
            "GENERAL OVERVIEW of what is happening in psychotherapy research — "
            "cover the most important and recent papers regardless of age group. "
            "Adult-focused psychotherapy work should NOT be downplayed. "
            "For each paper: methods (RCT design, comparator, blinding), effect "
            "sizes, attrition, and implementation feasibility. Where a paper "
            "obviously bears on child or adolescent practice (e.g. parent "
            "training, trauma-focused work, school-based intervention), add a "
            "brief connecting note — but do NOT let this drive selection. "
            "Generate the podcast entirely in Hebrew."
        ),
    },
    {
        # ── CLUSTER 8 ────────────────────────────────────────────────────────────────────
        # Behavioral sciences — learning, reinforcement, social cognition
        "id":       "behavioral_sciences",
        "label_en": "Behavioral Sciences",
        "label_he": "מדעי ההתנהגות",
        "journals": [
            "Behav Brain Sci",
            "Psychol Sci",
            "J Exp Psychol Gen",
            "Behav Neurosci",
        ],
        # No journal_filter — goal is a general overview of what is happening
        # in top behavioral-science journals, not only psychiatry-relevant work.
        "broad": [],
        "max_articles": 12,
        "podcast_prompt": (
            "Review this week's behavioral-science findings from the leading "
            "journals (Behavioral and Brain Sciences, Psychological Science, "
            "J Experimental Psychology: General, Behavioral Neuroscience). The "
            "goal is a GENERAL OVERVIEW of what is happening in the field — "
            "learning, reinforcement, social cognition, behavior — regardless "
            "of direct psychiatric relevance. "
            "Discuss each paper on its own terms: theoretical claim, "
            "experimental design, findings, and implications within behavioral "
            "science. Where a finding bears on child or adolescent psychiatry "
            "(learning mechanisms relevant to anxiety / conduct, reward "
            "processing in ADHD / addiction, social cognition in autism), add "
            "a brief connecting note — but do NOT let this drive paper selection. "
            "Generate the podcast entirely in Hebrew."
        ),
    },
    {
        # ── CLUSTER 9 ────────────────────────────────────────────────────────────────────
        # Cognition — cognitive psychology, cognitive neuroscience
        "id":       "cognition",
        "label_en": "Cognition & Cognitive Science",
        "label_he": "קוגניציה ומדעי הקוגניציה",
        "journals": [
            "Psychol Rev",
            "J Cogn Neurosci",
            "Cogn Psychol",
            "Cognition",
            "J Exp Child Psychol",
        ],
        # No journal_filter — goal is a general overview of what is happening
        # in top cognition journals, not only studies pre-filtered for child use.
        "broad": [],
        "max_articles": 12,
        "podcast_prompt": (
            "Review this week's cognitive-science findings from the top journals "
            "(Psychological Review, J Cognitive Neuroscience, Cognitive "
            "Psychology, Cognition, J Experimental Child Psychology). The goal "
            "is a GENERAL OVERVIEW of cognition research — cover the most "
            "important and recent papers regardless of direct psychiatric "
            "relevance. "
            "Discuss each paper on its own terms: the cognitive question, the "
            "paradigm, the findings, theoretical significance. Where a finding "
            "bears on child or adolescent psychiatry (executive function in "
            "ADHD, working memory deficits, attention, language development "
            "and developmental psychopathology), add a brief connecting note — "
            "but do NOT let this drive paper selection or how much time you "
            "spend on a paper. "
            "Generate the podcast entirely in Hebrew."
        ),
    },
    {
        # ── CLUSTER 10 ───────────────────────────────────────────────────────────────────
        # Child & adolescent miscellaneous (non-core journals, broad MeSH)
        "id":       "child_adolescent_misc",
        "label_en": "Child & Adolescent — Miscellaneous",
        "label_he": "ילדים ומתבגרים — מגוון",
        "journals": [],
        "broad": [
            # Broad MeSH — exclude core journals already covered by clusters 1+2
            '"child psychiatry"[MeSH] NOT "J Am Acad Child Adolesc Psychiatry"[Journal] NOT "J Child Psychol Psychiatry"[Journal] NOT "Eur Child Adolesc Psychiatry"[Journal] NOT "Child Adolesc Mental Health"[Journal] NOT "Lancet Child Adolesc Health"[Journal] NOT "JAMA Pediatr"[Journal]',
            '"adolescent psychiatry"[MeSH] NOT "J Am Acad Child Adolesc Psychiatry"[Journal] NOT "J Child Psychol Psychiatry"[Journal] NOT "Lancet Child Adolesc Health"[Journal]',
            '"autism spectrum disorder"[MeSH] AND ("child"[MeSH] OR "adolescent"[MeSH]) NOT "J Am Acad Child Adolesc Psychiatry"[Journal] NOT "J Child Psychol Psychiatry"[Journal]',
            '"attention deficit disorder with hyperactivity"[MeSH] NOT "J Am Acad Child Adolesc Psychiatry"[Journal] NOT "J Child Psychol Psychiatry"[Journal]',
            '"self-injurious behavior"[MeSH] AND "adolescent"[MeSH]',
            '"eating disorders"[MeSH] AND "adolescent"[MeSH]',
            '"anxiety disorders"[MeSH] AND ("child"[MeSH] OR "adolescent"[MeSH]) NOT "J Am Acad Child Adolesc Psychiatry"[Journal]',
        ],
        "max_articles": 10,
        "podcast_prompt": (
            "Discuss a varied set of child- and adolescent-related papers from this "
            "week — papers from journals not covered in the other reviews. Highlight "
            "interesting, surprising, or clinically meaningful findings. "
            "Generate the podcast entirely in Hebrew."
        ),
    },
]


# ── Per-cluster spoken intro (natural Hebrew, no jargon) ─────────────────────
# After the AI disclaimer, the hosts say one of these sentences so the listener
# knows what kind of episode this is — WITHOUT announcing an internal cluster
# name like "the core journals cluster". Phrased as something a human host
# would naturally say. Keyed by topic_id. Spotlights and split-parts are
# handled separately (a spotlight already says "this episode is about one
# review"; split parts inherit the base cluster's intro).
CLUSTER_INTRO_HE: dict[str, str] = {
    "child_adolescent_core":
        "בפרק הזה נסקור את המאמרים שפורסמו השבוע בכתבי העת המרכזיים של "
        "פסיכיאטריית הילד והמתבגר.",
    "child_adolescent_highimpact":
        "בפרק הזה נתמקד במאמרים שנוגעים לפסיכיאטריה של הילד והמתבגר, "
        "אך פורסמו דווקא בכתבי העת המובילים של הרפואה הכללית.",
    "child_adolescent_misc":
        "בפרק הזה נביא מבחר מאמרים בנושאי ילדים ומתבגרים שראו אור השבוע "
        "בכתבי עת נוספים בתחום.",
    "child_development":
        "בפרק הזה נעסוק במחקרים חדשים בהתפתחות הילד — התקשרות, ויסות רגשי, "
        "טראומה והשלכותיהם על הבנת התפתחות תקינה ופתולוגית.",
    "general_psychiatry_clinical":
        "בפרק הזה נסקור את המחקרים הקליניים החשובים שפורסמו השבוע "
        "בפסיכיאטריה הכללית של המבוגר.",
    "general_psychiatry_bio":
        "בפרק הזה נעסוק במחקר הביולוגי והפסיכופרמקולוגי העדכני — מנגנונים, "
        "גנטיקה וטיפול תרופתי.",
    "neuroscience":
        "בפרק הזה נסקור את הממצאים הבולטים שפורסמו השבוע בכתבי העת המובילים "
        "של מדעי המוח, ונבחן את הרלוונטיות שלהם לפסיכיאטריה.",
    "psychotherapy":
        "בפרק הזה נסקור את המחקרים החשובים שפורסמו השבוע בתחום הפסיכותרפיה "
        "וההתערבויות הטיפוליות.",
    "behavioral_sciences":
        "בפרק הזה נעסוק בממצאים מתחום מדעי ההתנהגות — למידה, חיזוק וקוגניציה "
        "חברתית — ובזיקתם לפסיכיאטריה.",
    "cognition":
        "בפרק הזה נסקור מחקרים עדכניים בקוגניציה — תפקודים ניהוליים, קשב, "
        "זיכרון עבודה ושפה — ובקשר שלהם לפסיכופתולוגיה.",
}


def _intro_directive_for(topic_id: str) -> str:
    """Return the prompt directive that tells the hosts to open with this
    cluster's natural-language intro. Empty string if no intro is defined
    (e.g. spotlights). Split-part topic_ids (`..._part2`) fall back to the
    base cluster's intro."""
    base = topic_id.split("_part")[0] if "_part" in topic_id else topic_id
    intro = CLUSTER_INTRO_HE.get(base)
    if not intro:
        return ""
    return (
        "\n\n"
        "========================================================================\n"
        "WHAT KIND OF EPISODE THIS IS (say right after the disclaimer, in Hebrew):\n"
        "========================================================================\n"
        "Right after the disclaimer, orient the listener to what this episode "
        "covers — naturally, in the hosts' own words, conveying this idea:\n"
        f"  \"{intro}\"\n"
        "Weave it into the opening; do not read it robotically or name an "
        "internal category.\n"
    )


# ── Shared tone / structure guidance — appended to every podcast prompt ──────
# Lives separately so we can edit once and have it apply to all clusters
# (regular + spotlight). Written in English for instruction fidelity; the
# Hebrew disclaimer is given verbatim because that's what listeners hear.
#
# DESIGN NOTE (why this is deliberately short): NotebookLM's audio model
# degrades when the prompt piles on many competing "MANDATORY" blocks — it
# rushes to satisfy all of them and starts clipping sentences mid-thought
# ("the jumps"). We keep ONLY the rules that measurably matter and state each
# once. The single most important quality rule — unhurried pace + complete
# sentences — is placed FIRST so it isn't buried.
TONE_GUIDANCE = (
    "\n\n"
    "========================================================================\n"
    "HOW TO SPEAK (most important — read first):\n"
    "========================================================================\n"
    "Speak at a calm, unhurried pace. There is no need to rush or to cram — "
    "take the time each point needs. Every sentence must be COMPLETE and "
    "well-formed: never start a thought and jump to the next one, never cut a "
    "sentence off, never leave a fragment or a half-word hanging. It is far "
    "better to say less, fully, than more, in broken pieces.\n"
    "This is a TWO-HOST Hebrew conversation. Keep it a real dialogue: the hosts "
    "genuinely alternate — one never delivers both sides or answers their own "
    "question. Keep each host's voice stable start to finish. Hebrew is "
    "gendered: each host addresses the other with the correct gender forms "
    "CONSISTENTLY (a male addressing a female says 'את אמרת'; a female "
    "addressing a male says 'אתה אמרת') — never flip mid-episode.\n"
    "\n"
    "========================================================================\n"
    "MANDATORY OPENING — say this FIRST, verbatim, calmly:\n"
    "========================================================================\n"
    "'הפודקאסט הבא נוצר באופן אוטומטי באמצעות בינה מלאכותית. התוכן עלול להכיל "
    "אי-דיוקים, פרשנויות שגויות או המצאות. אין להסתמך עליו לקבלת החלטות "
    "קליניות. חובה לבדוק כל פרט באופן עצמאי מול המקור המקורי.'\n"
    "\n"
    "Then open with a short framing (1-2 min) anchored in a SPECIFIC paper or "
    "question from THIS WEEK's papers — a tension between two findings, or a "
    "clinically actionable question they raise. Do NOT explain what child "
    "psychiatry is (the audience is a resident), and do NOT reuse the same "
    "generic opening as previous weeks. Anchoring it in this week's papers "
    "keeps it fresh automatically.\n"
    "\n"
    "========================================================================\n"
    "FOR EVERY PAPER, state two things:\n"
    "========================================================================\n"
    "1. The journal, by its FULL name, not its abbreviation. The source lists "
    "each as 'Full Name (Abbrev)' — read the full name aloud (say 'Journal of "
    "Child Psychology and Psychiatry', not 'J Child Psychol Psychiatry').\n"
    "2. The study type, taken verbatim from the 'סוג מחקר:' field in the source "
    "(מטה-אנליזה, RCT, מחקר עוקבה, וכו'). Do not guess. If it says the generic "
    "'מאמר מחקרי', infer a more specific design from the abstract if you can. "
    "Study type matters — an RCT weighs differently than a case report.\n"
    "\n"
    "========================================================================\n"
    "COVERAGE, CONTINUITY, TONE:\n"
    "========================================================================\n"
    "Cover EVERY paper in the source — none skipped. Give each its own time "
    "(methods, findings with effect sizes, limitations, clinical implications); "
    "do not compress several papers into one sentence.\n"
    "If the source ends with a 'משבוע שעבר' section, those papers were covered "
    "LAST week — do not re-summarize them. Use them only to draw a brief "
    "connection when a paper THIS week extends or contradicts them; otherwise "
    "ignore the section.\n"
    "Keep the tone professional and measured. Avoid superlatives "
    "('groundbreaking', 'revolutionary'); always name limitations and effect "
    "sizes. The gap between 'effective' and 'highly effective' matters.\n"
)


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


# ── Non-research PubTypes — articles to DROP from the feed ───────────────────
# These pubtype labels mark content that isn't original research: letters
# to the editor, editorials, errata, pre-registration protocols (no results
# yet), news items, biographies, etc. If ANY of an article's PubMed pubtype
# strings matches this set (case-insensitive), the article is dropped at
# _esummary time and never reaches the markdown / podcast pipeline.
# Case Reports are NOT excluded — they're primary clinical research, even
# at n=1.
EXCLUDED_PUBTYPES: set[str] = {
    # Non-research correspondence
    "letter", "comment", "editorial",
    # Errata and retractions
    "published erratum", "erratum", "correction",
    "retraction of publication", "retracted publication",
    # News and opinion pieces
    "news", "newspaper article",
    # Biography / autobiography / interviews
    "biography", "autobiography", "interview",
    # Lectures and addresses
    "lectures", "address",
    # Patient-education and similar
    "patient education handout",
    # Protocols — pre-registration, no results yet
    "clinical trial protocol", "research protocol", "study protocol",
    # Personal narrative / opinion essays
    "personal narrative",
    # Multimedia / non-text
    "webcasts", "video-audio media",
}


# ── Study-type classification (PubMed pubtype → Hebrew label) ─────────────────
# PubMed returns a `pubtype` list per article, often with multiple values
# (e.g. ["Journal Article", "Review", "Systematic Review"]). We pick the
# MOST informative one and translate to Hebrew so listeners hear concrete
# methodology ("מטה-אנליזה", "RCT", "מחקר עוקבה") instead of generic
# "מאמר מחקרי".
STUDY_TYPE_PRIORITY: list[tuple[str, str]] = [
    # (substring to match in pubtype — case-insensitive, Hebrew label)
    ("meta-analysis",               "מטה-אנליזה"),
    ("systematic review",           "סקירה שיטתית"),
    ("randomized controlled trial", "RCT (מחקר אקראי מבוקר)"),
    ("clinical trial, phase iii",   "מחקר קליני שלב 3"),
    ("clinical trial, phase ii",    "מחקר קליני שלב 2"),
    ("clinical trial, phase i",     "מחקר קליני שלב 1"),
    ("clinical trial",              "מחקר קליני"),
    ("multicenter study",           "מחקר רב-מרכזי"),
    ("observational study",         "מחקר תצפיתי"),
    ("cohort studies",              "מחקר עוקבה"),
    ("case-control studies",        "מחקר מקרה-ביקורת"),
    ("cross-sectional studies",     "מחקר חתך"),
    ("validation study",            "מחקר ולידציה"),
    ("comparative study",           "מחקר השוואתי"),
    ("practice guideline",          "הנחיות קליניות"),
    ("guideline",                   "הנחיות קליניות"),
    ("consensus development",       "מסמך קונצנזוס"),
    ("case reports",                "תיאור מקרה"),
    ("review",                      "מאמר סקירה"),
    ("editorial",                   "מאמר מערכת"),
    ("comment",                     "תגובה / commentary"),
    ("letter",                      "מכתב למערכת"),
    ("news",                        "ידיעה"),
]


def classify_study_type_he(pubtypes: list[str]) -> str:
    """Pick the most informative study type from PubMed pubtype list and
    translate to Hebrew. Falls back to a generic label if none match."""
    if not pubtypes:
        return "מאמר מחקרי"
    types_lower = [str(t).lower() for t in pubtypes]
    for needle, he_label in STUDY_TYPE_PRIORITY:
        if any(needle in t for t in types_lower):
            return he_label
    return "מאמר מחקרי"


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
    dropped_non_research = 0
    for pmid in pmids:
        if pmid == "uids":
            continue
        doc = result.get(pmid, {})
        if not doc or doc.get("error"):
            continue
        pubtypes = doc.get("pubtype", []) or []

        # Drop non-research content (letters, editorials, errata, protocols,
        # news, etc.) — see EXCLUDED_PUBTYPES above for the full list.
        pubtypes_lower = {str(t).lower() for t in pubtypes}
        if pubtypes_lower & EXCLUDED_PUBTYPES:
            dropped_non_research += 1
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
            "pubtype":       pubtypes,
            "study_type_he": classify_study_type_he(pubtypes),
        })
    if dropped_non_research:
        print(f"    Dropped {dropped_non_research} non-research item(s) "
              f"(letters/editorials/protocols/errata)")
    return articles


def search_topic(topic: dict, exclude_pmids: set[str] | None = None) -> list[dict]:
    """Search PubMed for one topic.
    Journal-specific queries run first -> top journals are always represented.

    Supports two optional topic-level fields:
      * journal_filter — extra PubMed query string ANDed to every per-journal
        search. Used by clusters that pull from generalist journals
        (JAMA Pediatrics, Developmental Psychology) where we want only
        psychiatry / mental-health content.
      * _forced_articles — list of pre-fetched article dicts. When present,
        skip PubMed entirely and use them directly. Used by spotlight reviews
        so each chosen review gets its own dedicated notebook + podcast.

    `exclude_pmids` (if given) drops any article already covered in a recent
    weekly run, so the same paper doesn't reappear across consecutive weeks.
    """
    exclude_pmids = exclude_pmids or set()
    label = topic["label_en"]
    print(f"\n[{label}]")

    # Spotlight reviews: bypass PubMed search, use the article we already have
    if topic.get("_forced_articles"):
        articles = list(topic["_forced_articles"])
        for a in articles:
            a["impact_factor"] = get_journal_if(a["journal"])
        articles.sort(key=lambda a: -a["impact_factor"])
        print(f"  Spotlight: 1 review article forced into this notebook.")
        return articles

    seen: dict[str, bool] = {}   # pmid -> True, insertion-ordered
    journal_filter = (topic.get("journal_filter") or "").strip()
    skipped_dup = 0

    # 1. Journal-targeted searches (high priority)
    for journal in topic.get("journals", []):
        q = f'"{journal}"[Journal]'
        if journal_filter:
            q = f'{q} AND {journal_filter}'
        ids = _esearch(q, retmax=6)
        new = []
        for p in ids:
            if p in seen:
                continue
            if p in exclude_pmids:
                skipped_dup += 1
                continue
            seen[p] = True
            new.append(p)
        if new:
            print(f"  {journal}: {len(new)} article(s)")

    # 2. Broad MeSH/keyword searches (supplement)
    for query in topic.get("broad", []):
        ids = _esearch(query, retmax=8)
        for p in ids:
            if p in seen or p in exclude_pmids:
                if p in exclude_pmids and p not in seen:
                    skipped_dup += 1
                continue
            seen[p] = True

    if skipped_dup:
        print(f"  Skipped {skipped_dup} article(s) already covered in recent weeks")

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


# ── Step 1b: Spotlight reviews (one dedicated podcast per major review) ───────
# Important review articles (Stahl on antipsychotics, big meta-analyses, etc.)
# deserve their own podcast — when packed into a 10-paper cluster they get
# only a minute of airtime. This pass finds them and adds dedicated topics.

SPOTLIGHT_HIGH_SIGNAL_AUTHORS = [
    # Psychopharmacology
    "Stahl SM",
    # Translational psychiatry / neurodevelopment
    "Insel TR", "Cuthbert BN", "Pine DS", "Leibenluft E",
    # Child & adolescent psychiatry
    "Volkmar FR", "Rapoport JL", "Sonuga-Barke E", "Polanczyk GV",
    "Findling RL", "Vitiello B", "Wagner KD",
    # ADHD / pharmacology
    "Faraone SV", "Buitelaar JK", "Banaschewski T", "Coghill D",
    # Schizophrenia / psychosis
    "Correll CU", "Kahn RS", "Howes OD",
    # Neurobiology / circuits
    "Krystal JH", "Nestler EJ",
]

# Dedicated psychiatry journals — every review here is, by definition,
# psychiatric content. Generalist journals (BMJ / JAMA / Lancet / NEJM /
# Nature Medicine) used to be included with a title-keyword filter, but
# the filter still let through papers that touch psychiatry tangentially
# (e.g. a Lancet review on kidney health mentioning "mental health"
# comorbidity in the title). User decided to drop generalists entirely —
# Stahl-style breakthroughs in NEJM still get caught by the signal-author
# search below.
SPOTLIGHT_JOURNALS_PSYCHIATRY = [
    "JAMA Psychiatry", "Lancet Psychiatry", "World Psychiatry",
    "Am J Psychiatry", "Mol Psychiatry", "Biol Psychiatry",
    "Neuropsychopharmacology", "J Am Acad Child Adolesc Psychiatry",
    "Lancet Child Adolesc Health",
    # ECNP's translational neuroscience journal — explicitly psychiatric scope
    "Neuroscience Applied",
]

# ── Spotlight selection tuning ────────────────────────────────────────────────
# Spotlights used to be REVIEWS ONLY. Broadened 2026-07 (user request): now
# ANY high-signal article from a top-tier journal can earn a dedicated deep-dive
# — a landmark RCT, a major cohort, a practice guideline, or a meta-analysis.
# The gate is an importance SCORE (study design + journal impact factor + signal
# author), not the publication type alone. Spotlights now live in their OWN RSS
# channels (child / psychiatry / therapy spotlight), so we can afford more of
# them — but we cap PER AREA so one field doesn't crowd out the others, and cap
# the weekly TOTAL to stay under NotebookLM's generation rate limits (the reason
# the weekly run is also split across two days: reviews one day, spotlights
# another). All three numbers are ceilings, NOT targets — a quiet week yields
# fewer; we never fabricate.
SPOTLIGHT_MIN_SCORE       = 4   # minimum importance score to earn a spotlight
MAX_SPOTLIGHT_PER_CHANNEL = 3   # ceiling per area (child / psychiatry / therapy)
MAX_SPOTLIGHT_TOTAL       = 8   # ceiling across all areas in one run
# Back-compat alias — older helper scripts may import MAX_SPOTLIGHT_REVIEWS.
MAX_SPOTLIGHT_REVIEWS     = MAX_SPOTLIGHT_TOTAL


# Spotlights are now SELECTED FROM the weekly review articles (2026-07), not
# from a separate psychiatry-only search. Each review cluster maps to one
# spotlight channel; we pick the top-scoring reviewed papers per channel. This
# guarantees every domain (neuroscience, psychotherapy, cognition, development —
# not just psychiatry) can earn a spotlight, drawn from its own journals.
CLUSTER_TO_SPOTLIGHT_CHANNEL: dict[str, str] = {
    "child_adolescent_core":        "child",
    "child_adolescent_highimpact":  "child",
    "child_adolescent_misc":        "child",
    "child_development":            "child",
    "general_psychiatry_clinical":  "psychiatry",
    "general_psychiatry_bio":       "psychiatry",
    "neuroscience":                 "psychiatry",
    "psychotherapy":                "therapy",
    "cognition":                    "therapy",
    "behavioral_sciences":          "therapy",
}

# Human-readable channel name for spoken cross-references.
SPOTLIGHT_CHANNEL_HE: dict[str, str] = {
    "child":      "פסיכיאטריית הילד והמתבגר",
    "psychiatry": "פסיכיאטריה ומדעי המוח",
    "therapy":    "פסיכותרפיה וקוגניציה",
}

# Tier-1 eligibility gate: a paper may earn a spotlight only if it comes from a
# curated top journal of its domain. Built from the clusters' own journal lists
# (per-domain quality, so it doesn't penalise lower-IF psychotherapy journals)
# plus the elite psychiatry list. A paper from a broad-MeSH pull in a non-listed
# journal is reviewed but NOT spotlight-eligible.
SPOTLIGHT_ELIGIBLE_JOURNALS: set[str] = {
    j.lower().strip()
    for t in TOPICS for j in t.get("journals", [])
} | {j.lower().strip() for j in SPOTLIGHT_JOURNALS_PSYCHIATRY} | {
    # PubMed abbreviation variants of the above (PubMed's 'source' can differ
    # from our search term, e.g. it emits "Ment" for "Mental").
    "child adolesc ment health",
    "j am acad child adolesc psychiatry",
}


def _spotlight_eligible_journal(journal: str) -> bool:
    """Tier-1 gate: is this journal in the curated per-domain top-journal set?

    EXACT (normalized) match — deliberately NOT a loose substring match, so that
    short elite names like "Brain" don't wrongly admit "Brain Sci" / "Brain Res"
    etc. A paper whose journal abbreviation isn't recognised is simply not
    spotlight-eligible (it's still reviewed) — a safe miss."""
    name = (journal or "").lower().strip()
    return bool(name) and name in SPOTLIGHT_ELIGIBLE_JOURNALS


# Content-signal keywords (matched in title + abstract) that mark a paper as
# especially spotlight-worthy: a new drug, a new mechanism/target, or a
# policy/guideline document. These add to the importance score (tier-2 content).
_SPOT_KW_NEW_DRUG = [
    "first-in-class", "first in class", "newly approved", "fda approval",
    "new drug", "novel agent", "novel compound", "novel antidepressant",
    "novel antipsychotic", "novel treatment", "new treatment", "new medication",
]
_SPOT_KW_NEW_MECHANISM = [
    "novel mechanism", "new mechanism", "mechanism of action", "novel target",
    "new target", "therapeutic target", "novel pathway",
]
_SPOT_KW_POLICY = [
    "guideline", "practice parameter", "consensus statement", "consensus guideline",
    "recommendation", "policy statement", "position statement",
]


def _spotlight_score(article: dict, has_signal_author: bool) -> int:
    """Importance heuristic — higher = more spotlight-worthy.

    Tier-2 content score (tier-1 eligibility is the curated per-domain journal
    list, checked separately). Rewards strong study designs (meta-analysis, RCT,
    guideline), elite-journal impact factor, high-value content (new drug / new
    mechanism / policy), and named high-signal authors."""
    score = 0
    pts = [str(t).lower() for t in article.get("pubtype", [])]

    def has(*needles: str) -> bool:
        return any(n in t for t in pts for n in needles)

    # Study design.
    if has("meta-analysis"):
        score += 3
    elif has("systematic review"):
        score += 3
    if has("practice guideline", "guideline", "consensus"):
        score += 3
    if has("randomized controlled trial", "clinical trial, phase iii"):
        score += 3
    elif has("clinical trial", "multicenter study"):
        score += 2
    elif has("cohort", "observational", "case-control", "cross-sectional"):
        score += 1   # original research design — modest signal
    if score == 0 and has("review"):
        score += 1   # narrative review with no stronger signal

    # Journal impact factor.
    if_val = article.get("impact_factor", 0.0)
    if if_val >= 40:        # Lancet Psychiatry, World Psychiatry, NEJM, Lancet
        score += 3
    elif if_val >= 20:      # JAMA Psychiatry, JAMA Pediatrics
        score += 2
    elif if_val >= 10:      # AJP, Mol/Biol Psychiatry, JAACAP
        score += 1

    # High-value content (title + abstract keywords).
    text = f"{article.get('title', '')} {article.get('abstract', '')}".lower()
    if any(k in text for k in _SPOT_KW_NEW_DRUG):
        score += 2       # new drug / first-in-class
    if any(k in text for k in _SPOT_KW_NEW_MECHANISM):
        score += 2       # new mechanism / therapeutic target
    if any(k in text for k in _SPOT_KW_POLICY):
        score += 2       # policy / guideline (also caught by pubtype above; ok)

    if has_signal_author:
        score += 2
    return score


def _has_signal_author(article: dict) -> bool:
    """True if any high-signal author appears in the article's author string."""
    authors_lc = article.get("authors", "").lower()
    return any(name.lower() in authors_lc for name in SPOTLIGHT_HIGH_SIGNAL_AUTHORS)


def _esearch_reldate(query: str, reldate: int, retmax: int = 12) -> list[str]:
    """esearch variant with caller-specified reldate window."""
    try:
        r = requests.get(PUBMED_BASE + "esearch.fcgi", params={
            "db": "pubmed", "term": query,
            "reldate": reldate, "datetype": "edat",
            "retmax": retmax, "retmode": "json", "sort": "relevance",
        }, timeout=30)
        r.raise_for_status()
        return r.json().get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        print(f"    Warning: esearch error: {e}")
        return []
    finally:
        time.sleep(0.4)


def _spotlight_prompt(a: dict, review_channel_he: str = "") -> str:
    """Single-paper deep-dive prompt, adapted to the article's study type.
    Covers trials, cohorts, guidelines, reviews. `review_channel_he` (when set)
    adds a spoken cross-reference back to the weekly-review channel that briefly
    covered this same paper a few days earlier."""
    xref = ""
    if review_channel_he:
        xref = (
            "\n\n"
            "CROSS-REFERENCE (say once, naturally, near the start): this same "
            f"paper was covered briefly in this week's weekly-review episode of "
            f"\"{review_channel_he}\". Listeners who heard the overview will "
            "recognise it; this dedicated episode goes deeper because the paper "
            "is especially important. Do NOT name a specific episode title.\n"
        )
    return (
        f"This is a DEDICATED, single-paper deep-dive podcast on one "
        f"high-signal article:\n"
        f"  Title: \"{a['title']}\"\n"
        f"  Authors: {a['authors']}\n"
        f"  Journal: {a['journal']} (IF: {a['impact_factor']:.1f})\n"
        f"  Study type: {a.get('study_type_he', 'מאמר')}\n\n"
        "Treat this as a LONG, comprehensive single-paper episode — every part "
        "of the paper deserves real discussion. Cover, ADAPTING to the study "
        "type:\n"
        "  • The clinical or scientific question the paper addresses.\n"
        "  • The methodology — for a randomized trial: design, randomization, "
        "blinding, comparator, primary/secondary outcomes, effect sizes, NNT, "
        "adverse events, attrition; for a meta-analysis / systematic review: "
        "search strategy, inclusion criteria, risk-of-bias, heterogeneity (I²), "
        "publication bias; for a cohort / observational study: sample, "
        "follow-up, confounders, and causal caveats; for a practice guideline: "
        "the key recommendations and the strength of evidence behind each; for "
        "a narrative review: the author's framework.\n"
        "  • The main findings with the actual numbers, and how certain they are.\n"
        "  • Controversies, counter-arguments, and the limitations.\n"
        "  • Clinical implications — for a child/adolescent psychiatry resident, "
        "what should change in practice, what stays uncertain, what to do "
        "differently tomorrow morning.\n"
        "If this is a Stahl-style psychopharmacology paper, name the receptors, "
        "mechanisms, pharmacokinetics, and clinical pearls carefully.\n"
        "Generate the podcast entirely in Hebrew."
        + xref
    )


def build_spotlight_topic(rec: dict) -> dict:
    """Build a TOPICS-shaped topic dict from a selection record
    {pmid, channel, score, source_topic_id, article}. The article carries a
    `spotlight_channel` field so save_articles_json + generate_rss route it to
    the right spotlight feed (no keyword guessing)."""
    a = dict(rec["article"])
    channel = rec["channel"]
    a["spotlight_channel"] = channel
    pmid = str(a["pmid"])
    title_short = a["title"][:50] + ("…" if len(a["title"]) > 50 else "")
    first_author = a["authors"].split(",")[0].replace(" et al.", "").strip()
    study_he = a.get("study_type_he") or "מאמר"
    return {
        "id":              f"spotlight_{pmid}",
        "label_en":        f"Spotlight: {first_author} — {title_short}",
        "label_he":        f"{study_he}: {first_author} — {title_short}",
        "journals":        [],
        "broad":           [],
        "max_articles":    1,
        "_forced_articles": [a],
        "spotlight_channel": channel,
        "podcast_prompt":  _spotlight_prompt(
            a, review_channel_he=SPOTLIGHT_CHANNEL_HE.get(channel, ""),
        ),
    }


def select_spotlights(nb_infos: list[dict]) -> list[dict]:
    """Pick the spotlight papers FROM this run's review articles.

    Tier-1 gate: the paper's journal is in the curated per-domain top-journal
    set (_spotlight_eligible_journal). Tier-2: importance score (_spotlight_
    score). Each review cluster maps to one channel (CLUSTER_TO_SPOTLIGHT_
    CHANNEL); we take the top MAX_SPOTLIGHT_PER_CHANNEL papers per channel,
    guaranteeing every domain is represented, not just psychiatry.

    Returns selection records: {pmid, channel, score, source_topic_id, article}.
    """
    by_channel: dict[str, list[tuple]] = {"child": [], "psychiatry": [], "therapy": []}
    for nb in nb_infos:
        base = nb["topic"]["id"].split("_part")[0]
        if base.startswith("spotlight_"):
            continue
        channel = CLUSTER_TO_SPOTLIGHT_CHANNEL.get(base)
        if not channel:
            continue
        for a in nb["articles"]:
            if not _spotlight_eligible_journal(a.get("journal", "")):
                continue
            s = _spotlight_score(a, _has_signal_author(a))
            if s >= SPOTLIGHT_MIN_SCORE:
                by_channel[channel].append((s, a, nb["topic"]["id"]))

    selection: list[dict] = []
    seen: set[str] = set()
    for channel in ("child", "psychiatry", "therapy"):
        cands = sorted(
            by_channel[channel],
            key=lambda x: (-x[0], -x[1].get("impact_factor", 0.0)),
        )
        picked = 0
        for s, a, tid in cands:
            if picked >= MAX_SPOTLIGHT_PER_CHANNEL:
                break
            pmid = str(a.get("pmid", ""))
            if not pmid or pmid in seen:
                continue
            seen.add(pmid)
            selection.append({
                "pmid": pmid, "channel": channel, "score": s,
                "source_topic_id": tid, "article": a,
            })
            picked += 1

    counts = {c: sum(1 for r in selection if r["channel"] == c)
              for c in ("child", "psychiatry", "therapy")}
    print(f"  Spotlight selection: {len(selection)} paper(s) "
          f"[child:{counts['child']} psychiatry:{counts['psychiatry']} "
          f"therapy:{counts['therapy']}]")
    for r in selection:
        a = r["article"]
        print(f"    • [{r['channel']}] score {r['score']} · {a['journal']} · "
              f"{a['title'][:55]}")
    return selection


def save_spotlight_selection(selection: list[dict], date_str: str) -> None:
    """Persist the spotlight selection so the spotlights run (a few days later)
    can generate exactly these papers — no fresh search, perfect sync with the
    reviews. Committed with the rest of summaries/<date>/."""
    out_dir = Path("summaries") / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    data = [{
        "pmid": r["pmid"], "channel": r["channel"], "score": r["score"],
        "source_topic_id": r["source_topic_id"], "article": r["article"],
    } for r in selection]
    (out_dir / "spotlight-selection.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(f"  Saved spotlight selection: "
          f"summaries/{date_str}/spotlight-selection.json ({len(data)} paper(s))")


def load_spotlight_selection(max_age_days: int = 6) -> list[dict]:
    """Load the most recent spotlight-selection.json from THIS week's reviews
    run (strictly before today, within max_age_days so we never resurrect an
    old week's selection). Returns [] if none is recent enough."""
    sum_dir = Path("summaries")
    if not sum_dir.exists():
        return []
    cutoff = (TODAY - timedelta(days=max_age_days)).strftime("%Y-%m-%d")
    dates: list[str] = []
    for sub in sum_dir.iterdir():
        if not sub.is_dir():
            continue
        try:
            datetime.strptime(sub.name, "%Y-%m-%d")
        except ValueError:
            continue
        if (sub.name < DATE_STR and sub.name >= cutoff
                and (sub / "spotlight-selection.json").exists()):
            dates.append(sub.name)
    if not dates:
        print("  No recent spotlight selection found "
              "(the reviews run may not have produced one).")
        return []
    date = max(dates)
    try:
        data = json.loads(
            (sum_dir / date / "spotlight-selection.json").read_text(encoding="utf-8")
        )
    except Exception as e:
        print(f"  Warning: could not read spotlight selection: {e}")
        return []
    print(f"  Loaded spotlight selection from {date}: {len(data)} paper(s).")
    return data if isinstance(data, list) else []


def wire_review_spotlight_xrefs(nb_infos: list[dict], selection: list[dict]) -> None:
    """Inject a spoken cross-reference into each REVIEW cluster whose articles
    include a paper chosen for a spotlight, so the review episode tells listeners
    a dedicated deep-dive is coming in the matching spotlight channel."""
    if not selection:
        return
    sel_pmids = {r["pmid"] for r in selection}
    n = 0
    for nb in nb_infos:
        if nb["topic"]["id"].split("_part")[0].startswith("spotlight_"):
            continue
        titles = [a.get("title", "") for a in nb["articles"]
                  if str(a.get("pmid", "")) in sel_pmids]
        if not titles:
            continue
        directive = (
            "\n\n"
            "========================================================================\n"
            "CROSS-REFERENCE (say naturally when you reach the paper):\n"
            "========================================================================\n"
            "One or more papers in this review will ALSO get their own dedicated, "
            "in-depth 'spotlight' episode in a few days, in the matching spotlight "
            "channel, because they are especially important. When you reach such a "
            "paper, cover it here as part of the review and invite interested "
            "listeners to hear the deep-dive in the spotlight channel. The papers:\n"
            + "".join(f"  • \"{t}\"\n" for t in titles)
        )
        nb["xref_directive"] = nb.get("xref_directive", "") + directive
        n += 1
    if n:
        print(f"  Wired spotlight cross-references into {n} review cluster(s).")


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


def _fetch_abstract_xml(pmid: str) -> str:
    """Fetch a PubMed abstract via the XML endpoint and assemble it.

    The XML format is far more reliable than the plain-text rendering — it
    explicitly tags AbstractText elements (and labels structured-abstract
    sections like BACKGROUND / METHODS / RESULTS / CONCLUSIONS), so we never
    have to guess where the abstract starts or ends.
    """
    import xml.etree.ElementTree as ET
    try:
        r = requests.get(PUBMED_BASE + "efetch.fcgi", params={
            "db": "pubmed", "id": pmid,
            "rettype": "abstract", "retmode": "xml",
        }, timeout=20)
        if r.status_code != 200:
            return "(Abstract not available)"
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError:
            return "(Abstract not available)"

        parts: list[str] = []
        for elem in root.iter("AbstractText"):
            label = (elem.get("Label") or "").strip()
            text = " ".join(elem.itertext()).strip()
            if not text:
                continue
            parts.append(f"{label.upper()}: {text}" if label else text)
        return "\n\n".join(parts) if parts else "(Abstract not available)"
    except Exception:
        return "(Abstract not available)"


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

        # Fall back to abstract — uses XML format for reliable parsing of
        # structured abstracts (BACKGROUND / METHODS / RESULTS / CONCLUSIONS).
        article["abstract"] = _fetch_abstract_xml(pmid)

        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(articles)} done  (full-text: {pmc_count})")
        time.sleep(1.2)

    print(f"  Done: {pmc_count}/{len(articles)} articles with PMC full text.")
    return articles

# ── Step 2b: Load previous week's articles (continuity / "Last Week" section) ─
def load_previous_week_articles() -> dict[str, list[dict]]:
    """Find the most recent past articles.json (strictly before DATE_STR) and
    return its articles grouped by topic_id.

    The articles.json is committed to the repo every week, so any past run's
    data is available on disk. Used to add a "משבוע שעבר" section to each
    cluster's Markdown summary — gives NotebookLM context for continuity
    without re-covering the same papers.

    Returns an empty dict if there is no previous week or the file is missing.
    """
    sum_dir = Path("summaries")
    if not sum_dir.exists():
        return {}

    # Find all YYYY-MM-DD subdirs strictly before today's date
    past_dates: list[str] = []
    for sub in sum_dir.iterdir():
        if not sub.is_dir():
            continue
        try:
            datetime.strptime(sub.name, "%Y-%m-%d")
        except ValueError:
            continue
        if sub.name < DATE_STR:
            past_dates.append(sub.name)

    if not past_dates:
        return {}

    past_dates.sort(reverse=True)
    for date_str in past_dates:
        json_file = sum_dir / date_str / "articles.json"
        if not json_file.exists():
            continue
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  Warning: could not load {json_file}: {e}")
            continue

        by_topic: dict[str, list[dict]] = {}
        for a in data:
            tid = a.get("topic_id", "")
            if tid:
                by_topic.setdefault(tid, []).append(a)
        print(f"  Loaded previous week ({date_str}): {len(data)} articles across {len(by_topic)} topics.")
        return by_topic

    return {}


def load_recent_pmids(weeks_back: int = 4, kinds: str = "all") -> set[str]:
    """Return the set of PMIDs covered in the last `weeks_back` weekly runs.

    Used to deduplicate: any article already discussed in a recent episode is
    dropped from this week's search so the same paper doesn't reappear across
    consecutive weeks.

    `kinds` picks WHICH past episodes count toward the dedup set, keyed on each
    article's topic_id in articles.json:
      * "reviews"    — only past REVIEW clusters (topic_id NOT starting with
                       'spotlight_'). Reviews dedup against this so a paper isn't
                       repeated in the review channel two weeks running — but
                       crucially NOT against past spotlights, so getting a
                       spotlight NEVER removes a paper from the review episodes.
      * "spotlights" — only past SPOTLIGHTS (topic_id starting with 'spotlight_').
                       Spotlights dedup against this so the same paper isn't
                       spotlighted two weeks running — but NOT against reviews,
                       so a paper covered in this week's review can still earn
                       its own dedicated spotlight.
      * "all"        — every past PMID (legacy behaviour, used by mode="all").

    Reads the committed summaries/<date>/articles.json files. Only counts the
    `weeks_back` most-recent past dates (so the set stays bounded and we don't
    suppress a genuinely-recurring topic forever)."""
    sum_dir = Path("summaries")
    if not sum_dir.exists():
        return set()

    past_dates: list[str] = []
    for sub in sum_dir.iterdir():
        if not sub.is_dir():
            continue
        try:
            datetime.strptime(sub.name, "%Y-%m-%d")
        except ValueError:
            continue
        if sub.name < DATE_STR:
            past_dates.append(sub.name)

    past_dates.sort(reverse=True)
    recent = past_dates[:weeks_back]

    def _kind_matches(topic_id: str) -> bool:
        is_spot = str(topic_id).startswith("spotlight_")
        if kinds == "reviews":
            return not is_spot
        if kinds == "spotlights":
            return is_spot
        return True  # "all"

    pmids: set[str] = set()
    for date_str in recent:
        json_file = sum_dir / date_str / "articles.json"
        if not json_file.exists():
            continue
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        for a in data:
            if not _kind_matches(a.get("topic_id", "")):
                continue
            pmid = str(a.get("pmid", "")).strip()
            if pmid:
                pmids.add(pmid)

    if pmids:
        print(f"  Dedup ({kinds}): {len(pmids)} PMIDs seen in last "
              f"{len(recent)} week(s) will be skipped.")
    return pmids


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
                "pubtype":       a.get("pubtype", []),
                "study_type_he": a.get("study_type_he", "מאמר מחקרי"),
                # Set on spotlight articles so generate_rss routes them to the
                # right spotlight feed by the channel assigned on the reviews day
                # (no keyword guessing). Absent/None on regular review articles.
                "spotlight_channel": a.get("spotlight_channel"),
            })
    out_path = out_dir / "articles.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved: {out_path}  ({len(data)} articles)")


# ── Step 3b: Create per-topic Markdown summary ─────────────────────────────────
def create_topic_summary(
    topic: dict,
    articles: list[dict],
    prev_week_articles: list[dict] | None = None,
) -> str:
    """Write summaries/{DATE}/{topic_id}.md and return the path string.

    If `prev_week_articles` is provided (top papers from the same topic in last
    week's run), a "משבוע שעבר" section is appended at the end as context.
    The podcast prompt instructs NotebookLM not to re-cover those papers as
    new content, but to draw connections when this week's papers extend or
    relate to them.
    """
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
        # Generous limit (2000 chars) so NotebookLM gets the full structured
        # abstract (BACKGROUND / METHODS / RESULTS / CONCLUSIONS) per paper \u2014
        # this is what drives podcast depth.
        if len(abstract) > 2000:
            abstract = abstract[:2000] + "\u2026"
        if_val = a.get("impact_factor", 0)
        # Show the full journal name so NotebookLM reads it aloud properly,
        # with the abbreviation in parentheses for reference.
        full_jrnl = journal_full_name(a["journal"])
        jrnl_display = (
            f"{full_jrnl} ({a['journal']})"
            if full_jrnl != a["journal"] else a["journal"]
        )
        if if_val > 0:
            journal_str = f"{if_badge(if_val)} {jrnl_display} *(IF: {if_val:.1f})*"
        else:
            journal_str = f"\U0001f4c4 {jrnl_display}"
        study_type = a.get("study_type_he") or "\u05de\u05d0\u05de\u05e8 \u05de\u05d7\u05e7\u05e8\u05d9"
        lines += [
            f"### {a['title']}",
            f"**\u05db\u05ea\u05d1 \u05e2\u05ea:** {journal_str} | **\u05e1\u05d5\u05d2 \u05de\u05d7\u05e7\u05e8:** {study_type} | **\u05de\u05d7\u05d1\u05e8\u05d9\u05dd:** {a['authors']} | **\u05ea\u05d0\u05e8\u05d9\u05da:** {a['pub_date']}",
            "",
            abstract,
            "",
            f"\U0001f517 [\u05e7\u05d9\u05e9\u05d5\u05e8 \u05dc\u05de\u05d0\u05de\u05e8 \u05d1-PubMed]({a['url']})",
            "",
            "---",
            "",
        ]

    # \u2500\u2500 "Last Week" section \u2014 context for continuity \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    # Lists last week's top papers in this same topic. The podcast prompt tells
    # NotebookLM to use this as CONTEXT only (not new content), and to draw
    # connections when this week's papers extend / contradict / build on them.
    if prev_week_articles:
        top_prev = sorted(
            prev_week_articles,
            key=lambda a: -a.get("impact_factor", 0),
        )[:5]
        lines += [
            "",
            "---",
            "",
            "## \U0001f4c5 \u05de\u05e9\u05d1\u05d5\u05e2 \u05e9\u05e2\u05d1\u05e8 \u2014 \u05dc\u05e7\u05d5\u05e0\u05d8\u05e7\u05e1\u05d8 \u05d1\u05dc\u05d1\u05d3",
            "",
            "> \u05d4\u05de\u05d0\u05de\u05e8\u05d9\u05dd \u05d4\u05d1\u05d0\u05d9\u05dd \u05e0\u05d3\u05d5\u05e0\u05d5 \u05d1\u05e4\u05e8\u05e7 \u05d4\u05e7\u05d5\u05d3\u05dd \u05e9\u05dc \u05e0\u05d5\u05e9\u05d0 \u05d6\u05d4. "
            "**\u05d0\u05dc \u05ea\u05db\u05e1\u05d4 \u05d0\u05d5\u05ea\u05dd \u05db\u05ea\u05d5\u05db\u05df \u05d7\u05d3\u05e9.** "
            "\u05d0\u05dd \u05de\u05d0\u05de\u05e8 \u05de\u05d4\u05e9\u05d1\u05d5\u05e2 \u05d4\u05e0\u05d5\u05db\u05d7\u05d9 \u05de\u05de\u05e9\u05d9\u05da, \u05e1\u05d5\u05ea\u05e8 \u05d0\u05d5 \u05de\u05e8\u05d7\u05d9\u05d1 \u05de\u05d0\u05de\u05e8 \u05de\u05db\u05d0\u05df \u2014 \u05e6\u05d9\u05d9\u05df \u05d0\u05ea \u05d4\u05e7\u05e9\u05e8 \u05d1\u05e7\u05e6\u05e8\u05d4. "
            "\u05d0\u05d7\u05e8\u05ea \u2014 \u05d0\u05d9\u05df \u05e6\u05d5\u05e8\u05da \u05dc\u05d4\u05ea\u05d9\u05d9\u05d7\u05e1 \u05d0\u05dc\u05d9\u05d4\u05dd.",
            "",
        ]
        for a in top_prev:
            j = a.get("journal", "?")
            au = a.get("authors", "?")
            t = a.get("title", "?")
            lines.append(f"- **{j}** \u2014 {au} \u2014 *{t}*")
        lines.append("")

    lines += [
        "---",
        "",
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


def start_podcast(nb_id: str, prompt: str, env: dict,
                  topic_id: str = "") -> str | None:
    """Switch to notebook and fire off podcast generation.
    Returns artifact_id or None. Does NOT wait for completion.

    `topic_id` selects the per-cluster spoken intro injected between the
    base prompt and the shared TONE_GUIDANCE."""
    subprocess.run(
        ["notebooklm", "use", nb_id],
        capture_output=True, env=env, timeout=30,
    )
    full_prompt = prompt + _intro_directive_for(topic_id) + TONE_GUIDANCE
    try:
        out = subprocess.run([
            "notebooklm", "generate", "audio", full_prompt,
            "--format", "deep-dive", "--length", "long",
            "--language", "he", "--json",
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
                            nb["podcast_ready"]  = True
                            # NotebookLM auto-generates an engaging Hebrew
                            # title for each Deep Dive audio artifact (e.g.
                            # "מדידת הנפש מהיער ועד לגלי המוח"). Capture it
                            # so we can use it in the GitHub Release title
                            # and the RSS feed instead of the dry cluster
                            # label ("פסיכותרפיה והתערבויות").
                            nb["artifact_title"] = (a.get("title") or "").strip()
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
        # A "long" deep-dive podcast in Hebrew with 10 articles should be well
        # over 5 MB. Anything under ~3 MB usually means generation got cut
        # short or produced a tiny artifact — flag it so we can investigate.
        if size_mb < 3.0:
            print(f"  ⚠ WARNING: {topic_id} podcast is unusually small "
                  f"({size_mb:.1f} MB) — generation may have been truncated.")
        else:
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
def upload_to_github_release(
    podcast_path: str,
    topic: dict,
    env: dict,
    episode_number: int | None = None,  # kept for back-compat, unused now
    episode_total: int | None = None,   # kept for back-compat, unused now
    artifact_title: str | None = None,
    draft: bool = False,
) -> str | None:
    """Create a GitHub release for the episode. `draft=True` HOLDS it: draft
    releases are excluded from the RSS feed (generate_rss skips them), so the
    episode does NOT go to Spotify until a human publishes it (the QC gate for
    flagged episodes)."""
    tag    = f"weekly-{DATE_STR}-{topic['id']}"
    # Support both GitHub Actions (GITHUB_REPOSITORY) and Cloud Run (GH_REPO)
    repo   = env.get("GITHUB_REPOSITORY") or env.get("GH_REPO", "")
    server = env.get("GITHUB_SERVER_URL", "https://github.com")

    if not repo:
        print("  WARNING: GITHUB_REPOSITORY not set")
        return None

    # Episode display title:
    #   1. NotebookLM's auto-generated artifact title if we captured one
    #      (engaging, content-specific, e.g. "\u05de\u05d3\u05d9\u05d3\u05ea \u05d4\u05e0\u05e4\u05e9 \u05de\u05d4\u05d9\u05e2\u05e8 \u05d5\u05e2\u05d3 \u05dc\u05d2\u05dc\u05d9 \u05d4\u05de\u05d5\u05d7")
    #   2. Cluster label_he as fallback (the dry "\u05e4\u05e1\u05d9\u05db\u05d5\u05ea\u05e8\u05e4\u05d9\u05d4 \u05d5\u05d4\u05ea\u05e2\u05e8\u05d1\u05d5\u05d9\u05d5\u05ea")
    # No more (N/M) prefix \u2014 the channel/playlist split obsoletes it.
    display_title = (artifact_title or "").strip() or topic["label_he"]

    notes = (
        f"{topic['label_en']} weekly literature review {DATE_STR}\n\n"
        f"Cluster: {topic['label_he']}\n\n"
        f"*Generated automatically*"
    )
    if draft:
        notes += "\n\n\u23f8\ufe0f HELD by QC \u2014 pending human review before publishing."
    cmd = [
        "gh", "release", "create", tag, podcast_path,
        "--title", f"\U0001f4da {display_title} \u2014 {DATE_STR}",
        "--notes", notes,
        "--repo", repo,
    ]
    if draft:
        cmd.append("--draft")
    subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=180)

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
        # Prefer the NotebookLM artifact title (engaging, content-specific);
        # fall back to the cluster label when the artifact title is missing
        # (failed generation, etc.).
        nice_title = (nb.get("artifact_title") or "").strip() or nb["topic"]["label_he"]
        body_lines.append(f"  {icon} {nice_title}: {len(nb['articles'])} \u05de\u05d0\u05de\u05e8\u05d9\u05dd")
    if ready_podcasts:
        body_lines.append(f"\n\u2705 {ready_podcasts}/{len(nb_infos)} \u05e4\u05d5\u05d3\u05e7\u05d0\u05e1\u05d8\u05d9\u05dd \u05de\u05d5\u05db\u05e0\u05d9\u05dd.")

    # ntfy supports max 3 action buttons
    actions = []
    for nb in nb_infos:
        if nb.get("podcast_url") and len(actions) < 3:
            btn_title = (nb.get("artifact_title") or "").strip() or nb["topic"]["label_he"]
            # ntfy button labels work best under ~30 chars
            if len(btn_title) > 30:
                btn_title = btn_title[:29] + "\u2026"
            actions.append({
                "action": "view",
                "label":  f"\U0001f399\ufe0f {btn_title}",
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



# ── Cleanup old project notebooks ─────────────────────────────────────────────
def cleanup_old_notebooks(env: dict):
    """Delete [PsychReview] project notebooks older than 4 weeks.

    Only notebooks whose title starts with '[PsychReview]' are touched —
    personal notebooks are never deleted.
    """
    cutoff = TODAY - timedelta(weeks=4)
    print("\n\U0001f5d1\ufe0f  Cleaning up old [PsychReview] notebooks (older than 4 weeks)...")
    try:
        out = subprocess.run(
            ["notebooklm", "list", "--json"],
            capture_output=True, text=True, env=env, timeout=60,
        )
        data = json.loads(out.stdout.strip() or "{}")
        notebooks = data.get("notebooks", [])
    except Exception as e:
        print(f"  WARNING: Could not list notebooks for cleanup: {e}")
        return

    deleted = 0
    for nb in notebooks:
        title = nb.get("title", "")
        nb_id = nb.get("id", "")
        if not title.startswith("[PsychReview]") or not nb_id:
            continue
        # Extract date from end of title: "[PsychReview] ... \u2014 YYYY-MM-DD"
        m = re.search(r"(\d{4}-\d{2}-\d{2})$", title.strip())
        if not m:
            continue
        try:
            nb_date = datetime.strptime(m.group(1), "%Y-%m-%d")
        except ValueError:
            continue
        if nb_date < cutoff:
            result = subprocess.run(
                ["notebooklm", "delete", "-n", nb_id, "--yes"],
                capture_output=True, text=True, env=env, timeout=30,
            )
            if result.returncode == 0:
                print(f"  Deleted: {title}")
                deleted += 1
            else:
                print(f"  WARNING: Failed to delete {nb_id}: {result.stderr[:100]}")
    if deleted == 0:
        print("  No old project notebooks to delete.")
    else:
        print(f"  Deleted {deleted} old project notebook(s).")


# ── Drive backup + RSS feed (delegated to sibling scripts) ────────────────────
SCRIPTS_DIR = Path(__file__).resolve().parent


def backup_to_drive(env: dict) -> None:
    """Run scripts/backup_to_drive.py for today's folder. Non-fatal on failure."""
    if not env.get("GDRIVE_SERVICE_ACCOUNT_JSON") or not env.get("GDRIVE_FOLDER_ID"):
        return  # feature simply off — silent
    print("\n\U0001f4be Backing up to Google Drive...")
    try:
        subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "backup_to_drive.py"),
             "--date", DATE_STR],
            env=env, check=False, timeout=600,
        )
    except Exception as e:
        print(f"  WARNING: Drive backup failed (non-fatal): {e}")


def update_rss_feed(env: dict) -> None:
    """Regenerate all RSS feeds and commit + push the changes. Non-fatal.

    Note: we now produce multiple feeds (feed-child.xml, feed-psychiatry.xml,
    feed-therapy.xml) for the 3 topical Spotify shows. The old single
    feed.xml was retired in May 2026. The git-add glob below picks up all
    feed*.xml files so adding a new channel later doesn't break this step.
    """
    repo = env.get("GH_REPO") or env.get("GITHUB_REPOSITORY", "")
    if not repo:
        print("\n  RSS feed skipped: GH_REPO not set.")
        return
    print("\n\U0001f4e1 Updating podcast RSS feeds...")
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "generate_rss.py")],
            env=env, capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            print(f"  WARNING: generate_rss.py failed: {result.stderr[:200]}")
            return
        # Echo the feed builder's summary so the log shows per-feed counts.
        for line in result.stdout.splitlines()[-6:]:
            print(f"  {line}")

        # Stage every regenerated feed file. Glob handles both legacy and
        # current names (`feed.xml`, `feed-*.xml`).
        for feed_path in Path("docs").glob("feed*.xml"):
            subprocess.run(["git", "add", str(feed_path)], check=False)

        status = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], capture_output=True,
        )
        if status.returncode == 0:
            print("  No feed change to commit.")
            return
        subprocess.run(
            ["git", "commit", "-m", f"feed: update for {DATE_STR}"],
            capture_output=True, text=True, check=False,
        )
        push = subprocess.run(
            ["git", "push", "origin", "main"],
            capture_output=True, text=True, check=False,
        )
        if push.returncode == 0:
            print("  RSS feeds published.")
        else:
            print(f"  WARNING: git push failed: {push.stderr.strip()[:200]}")
    except Exception as e:
        print(f"  WARNING: RSS feed update failed (non-fatal): {e}")


def generate_digests(env: dict) -> None:
    """Run scripts/generate_digests.py — per-channel take-home files + a weekly
    clinical-questions file. Non-fatal. Writes into summaries/<date>/ so the
    subsequent commit_summaries_to_github() picks the files up. Skips itself
    (inside the script) when GEMINI_API_KEY is unset."""
    if not (env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")):
        return  # feature off — silent, like the Drive backup
    print("\n\U0001f4dd Generating weekly digests (take-home + clinical questions)...")
    try:
        subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "generate_digests.py"),
             "--date", DATE_STR],
            env=env, check=False, timeout=600,
        )
    except Exception as e:
        print(f"  WARNING: Digest generation failed (non-fatal): {e}")


def run_qc(env: dict) -> None:
    """Run scripts/qc_review.py — Gemini listens to each episode and scores it
    against the source abstracts, writing qc-report.md + qc-results.json (the
    latter drives the publish GATE). Non-fatal. Needs GEMINI_API_KEY; the script
    skips itself if it is missing. Committing is done later by the caller (one
    combined commit of the report + results + run-manifest)."""
    if not (env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")):
        return  # QC off — silent
    print("\n\U0001f50e Running podcast QC review...")
    try:
        subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "qc_review.py"),
             "--date", DATE_STR],
            env=env, check=False, timeout=3000,
        )
    except Exception as e:
        print(f"  WARNING: QC review failed (non-fatal): {e}")


# ── QC publish gate ───────────────────────────────────────────────────────────
# Only genuinely-bad episodes are HELD (uploaded as GitHub draft releases, which
# generate_rss excludes → they don't reach Spotify) pending a human decision.
# Clean and merely-"review" episodes publish automatically, so the weekly manual
# burden is tiny (~0-2 held/week). A human then publishes or regenerates a held
# episode via scripts/publish_episode.py / scripts/regenerate_episode.py.
QC_HOLD_ACCURACY_AT_OR_BELOW = 2


def load_qc_results() -> dict[str, dict]:
    """topic_id → {verdict, accuracy, ...} from summaries/<date>/qc-results.json.
    Empty dict when QC didn't run → nothing is held (everything publishes)."""
    path = Path("summaries") / DATE_STR / "qc-results.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _qc_should_hold(qc: dict | None) -> bool:
    if not qc:
        return False
    if qc.get("verdict") == "problem":
        return True
    acc = qc.get("accuracy")
    return isinstance(acc, int) and acc <= QC_HOLD_ACCURACY_AT_OR_BELOW


def save_run_manifest(nb_infos: list[dict]) -> None:
    """Persist per-episode {nb_id, full_prompt, held, release_tag} so the
    regenerate / publish tools can act on a specific episode later (the
    notebook survives ~4 weeks)."""
    out_dir = Path("summaries") / DATE_STR
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {}
    for nb in nb_infos:
        tid = nb["topic"]["id"]
        if not nb.get("nb_id"):
            continue
        data[tid] = {
            "nb_id":       nb["nb_id"],
            "full_prompt": nb.get("full_prompt", ""),
            "held":        bool(nb.get("held")),
            "release_tag": f"weekly-{DATE_STR}-{tid}",
            "label_he":    nb["topic"]["label_he"],
        }
    (out_dir / "run-manifest.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved run manifest ({len(data)} episode(s)).")


# ── Auto-split crowded topics into Part 1 / Part 2 / ... ─────────────────────
# If a cluster collected too many articles for one comfortable listen, split
# it into multiple parts. Each part becomes its own notebook + podcast +
# GitHub release, with `_part{N}` appended to the topic_id and "(חלק N/M)"
# appended to the Hebrew label. Articles are sorted by Impact Factor
# (descending) and divided round-robin among the parts so each part gets a
# balanced mix of high-IF papers rather than Part 1 hoarding the best.

SPLIT_THRESHOLD = 9    # split topics with more than this many articles
SPLIT_TARGET    = 7    # aim for ~this many articles per part
                       # Rationale: NotebookLM produces a roughly FIXED-length
                       # episode regardless of article count. The built-in
                       # `--length long` is already the maximum (options are
                       # only short/default/long, upper bound ~25 min) — asking
                       # the hosts to "be longer" does NOT extend it. So the
                       # ONLY lever against dense/shallow episodes is fewer
                       # articles per part. Lowered 13→9 (target 11→7) so each
                       # paper in a ~25-min episode gets ~3-4 min instead of
                       # being rushed. A crowded 20-article cluster now → 3
                       # parts of ~7; a normal ≤9 article cluster stays whole.
                       # NOTE: this produces MORE episodes per week — mitigated
                       # by splitting the weekly run across two days (reviews /
                       # spotlights) to stay under NotebookLM's rate limits.


def auto_split_topics(nb_infos: list[dict]) -> list[dict]:
    """Split any nb_info with too many articles into multiple parts."""
    new_infos: list[dict] = []
    for nb in nb_infos:
        articles = nb["articles"]
        topic    = nb["topic"]
        if len(articles) <= SPLIT_THRESHOLD:
            new_infos.append(nb)
            continue

        # Sort by IF descending so the highest-impact papers are spread evenly
        sorted_articles = sorted(
            articles, key=lambda a: -a.get("impact_factor", 0.0),
        )
        n_parts = max(2, (len(sorted_articles) + SPLIT_TARGET - 1) // SPLIT_TARGET)

        # Round-robin assignment — keeps IF distribution balanced across parts.
        chunks: list[list[dict]] = [[] for _ in range(n_parts)]
        for i, a in enumerate(sorted_articles):
            chunks[i % n_parts].append(a)

        print(f"  Split {topic['id']} ({len(articles)} articles) "
              f"→ {n_parts} parts of ~{len(chunks[0])} each")

        for part_idx, chunk in enumerate(chunks, start=1):
            new_topic = dict(topic)
            new_topic["id"]          = f"{topic['id']}_part{part_idx}"
            new_topic["label_he"]    = f"{topic['label_he']} — חלק {part_idx}/{n_parts}"
            new_topic["label_en"]    = f"{topic['label_en']} — Part {part_idx}/{n_parts}"
            new_topic["max_articles"] = len(chunk)
            # The prompt is identical across parts — the topic content is the
            # same, just split for length. Adding a note so NotebookLM knows
            # it's covering only a slice.
            new_topic["podcast_prompt"] = (
                topic["podcast_prompt"]
                + f"\n\n[NOTE: This is part {part_idx} of {n_parts} for this "
                f"topic. The source material contains only the papers assigned "
                f"to this part. Cover them as a coherent stand-alone episode "
                f"without referring to 'part 1' or 'part 2' explicitly.]"
            )

            new_infos.append({
                "topic":         new_topic,
                "articles":      chunk,
                "summary_path":  None,
                "nb_id":         None,
                "nb_url":        None,
                "artifact_id":   None,
                "podcast_ready": False,
                "podcast_path":  None,
                "podcast_url":   None,
            })
    return new_infos


def _clean_cluster_label(label_he: str) -> str:
    """Strip the ' — חלק N/M' split suffix to get the base cluster name,
    for use in cross-reference text ('הסקירה השבועית של פסיכיאטריה ביולוגית')."""
    for sep in (" — חלק", " - חלק", " — Part", " - Part"):
        if sep in label_he:
            return label_he.split(sep)[0].strip()
    return label_he.strip()


# (Old compute_cross_references() removed 2026-07: spotlight↔review cross-refs
#  are now wired directly — the review side by wire_review_spotlight_xrefs(), the
#  spotlight side by _spotlight_prompt(review_channel_he=...).)


# ── Main ───────────────────────────────────────────────────────────────────────
def main(mode: str = "all"):
    sep = "=" * 65
    mode_label = {
        "reviews":    "REVIEWS only (weekly clusters)",
        "spotlights": "SPOTLIGHTS only (single-paper deep-dives)",
        "all":        "ALL (reviews + spotlights)",
    }.get(mode, mode)
    print(f"\n{sep}")
    print(f"\U0001f4da Weekly Psychiatry Literature Review -- {DATE_STR}")
    print(f"   Mode: {mode_label}")
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
        print("Verifying & refreshing NotebookLM session...")

        # Try to refresh auth tokens first (fixes "session expired" issues)
        try:
            from notebooklm import NotebookLMClient
            import asyncio

            async def refresh_tokens():
                async with await NotebookLMClient.from_storage() as client:
                    tokens = await client.refresh_auth()
                    return tokens

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            tokens = loop.run_until_complete(refresh_tokens())
            loop.close()
            print(f"  ✓ Auth tokens refreshed")
        except Exception as e:
            print(f"  ⚠ Could not refresh tokens: {e}")

        # Now verify session with list command
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
            print("  ✓ Session verified and ready.")

    # ── Phase 1: Search + Summaries ───────────────────────────────────────────
    nb_infos: list[dict] = []
    all_articles: list[dict] = []

    def _mk_nb(topic: dict, articles: list[dict]) -> dict:
        return {
            "topic":         topic,
            "articles":      articles,
            "summary_path":  None,
            "nb_id":         None,
            "nb_url":        None,
            "artifact_id":   None,
            "podcast_ready": False,
            "podcast_path":  None,
            "podcast_url":   None,
        }

    do_reviews = mode in ("reviews", "all")
    print("\U0001f504 Loading recent PMIDs for deduplication...")

    # ── Review clusters ───────────────────────────────────────────────────────
    # Deduplicated against the last 4 weeks of REVIEWS (kinds="reviews") PLUS
    # this run's accumulating picks, so a paper matching two clusters lands only
    # in the first (highest-priority) one. NOT deduplicated against past
    # spotlights — a paper getting a spotlight must NOT be dropped from the
    # review episodes; the review channel covers everything in scope.
    if do_reviews:
        past_pmids = load_recent_pmids(weeks_back=4, kinds="reviews")
        week_pmids = set(past_pmids)
        print("\U0001f50d Searching PubMed for review clusters...")
        for topic in TOPICS:
            articles = search_topic(topic, exclude_pmids=week_pmids)
            if not articles:
                print(f"  WARNING: No articles for {topic['label_en']}, skipping.")
                continue
            for a in articles:
                week_pmids.add(str(a.get("pmid", "")))
            all_articles.extend(articles)
            nb_infos.append(_mk_nb(topic, articles))

    # ── Spotlights (Wednesday): generate from the reviews-day SELECTION ────────
    # Spotlights are the papers the REVIEWS run already chose a few days earlier,
    # from the same week's articles — NOT a fresh search. Perfect sync: every
    # spotlight paper was also reviewed. build_spotlight_topic() carries the
    # channel + the reverse cross-reference ("reviewed briefly this week").
    if mode == "spotlights":
        for rec in load_spotlight_selection():
            stopic = build_spotlight_topic(rec)
            arts = stopic["_forced_articles"]
            all_articles.extend(arts)
            nb_infos.append(_mk_nb(stopic, arts))

    if not nb_infos:
        # A spotlights-only run with no selection is NORMAL, not an error —
        # exit cleanly (exit 0) so the VM still backs up the session.
        if mode == "spotlights":
            print("No spotlight selection to produce this week — exiting cleanly.")
            return
        print("ERROR: No articles found in any topic!")
        send_notification([], env)
        sys.exit(1)

    # ── Auto-split crowded review clusters into Part 1 / Part 2 / ... ──────────
    nb_infos = auto_split_topics(nb_infos)

    # Fetch text for ALL articles in one pass (PMC full text when available).
    # Must run BEFORE spotlight selection so content-keyword scoring sees the
    # abstracts.
    fetch_article_text(all_articles)

    # ── Spotlight SELECTION (reviews day) ─────────────────────────────────────
    # From THIS run's review articles, pick the top spotlight-worthy papers per
    # channel (tier-1 journal gate + tier-2 content score) and SAVE the choice
    # so the spotlights run (a few days later) generates exactly these. Also wire
    # the review episodes to announce the upcoming spotlight. In "all" mode
    # (manual) we additionally build + generate the spotlights in this same run.
    if do_reviews:
        selection = select_spotlights(nb_infos)
        save_spotlight_selection(selection, DATE_STR)
        wire_review_spotlight_xrefs(nb_infos, selection)
        if mode == "all":
            for rec in selection:
                stopic = build_spotlight_topic(rec)
                arts = stopic["_forced_articles"]
                all_articles.extend(arts)
                nb_infos.append(_mk_nb(stopic, arts))

    # ── Assign episode numbers within this week's batch (after nb_infos final) ─
    total_episodes = len(nb_infos)
    for idx, nb in enumerate(nb_infos, start=1):
        nb["episode_number"] = idx
        nb["episode_total"]  = total_episodes
    print(f"\n📋 This week: {total_episodes} podcast episode(s) to produce.")

    # Save articles.json for web UI, then per-topic summaries.
    save_articles_json(nb_infos)

    # Load previous week's articles so each summary can include a "משבוע שעבר"
    # context section. Empty dict (and no section) if this is the first run.
    print("\n\U0001f4c5 Loading previous week for continuity...")
    prev_week = load_previous_week_articles()

    print("\n\U0001f4dd Creating topic summaries...")
    for nb in nb_infos:
        prev_for_topic = prev_week.get(nb["topic"]["id"], [])
        nb["summary_path"] = create_topic_summary(
            nb["topic"], nb["articles"], prev_for_topic,
        )

    # Weekly text digests (take-home messages per channel + clinical questions)
    # from the same abstracts. Written into summaries/<date>/ so the commit
    # below picks them up. No-op without GEMINI_API_KEY.
    generate_digests(env)

    # Commit summaries (and any digests) to GitHub regardless of NotebookLM status
    print("\n\U0001f4e4 Committing summaries to GitHub...")
    commit_summaries_to_github(env)

    if not has_notebooklm:
        print("\nWARNING: No NotebookLM session found -- skipping notebooks & podcasts")
        send_notification(nb_infos, env)
        return

    # ── Clean up old project notebooks (keep last 4 weeks) ─────────────────────
    cleanup_old_notebooks(env)

    # ── Phase 2: Create notebooks ─────────────────────────────────────────────
    print(f"\n\U0001f5d2\ufe0f  Creating {len(nb_infos)} notebooks...")
    for nb in nb_infos:
        ep = f"({nb['episode_number']}/{nb['episode_total']})"
        title = f"[PsychReview] {ep} {nb['topic']['label_he']} \u2014 {DATE_STR}"
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
            # Append any spotlight↔cluster cross-reference directive.
            base_prompt = nb["topic"]["podcast_prompt"] + nb.get("xref_directive", "")
            # Persist the FULL prompt (same one start_podcast builds internally)
            # so regenerate_episode.py can reproduce this episode faithfully.
            nb["full_prompt"] = (
                base_prompt + _intro_directive_for(nb["topic"]["id"]) + TONE_GUIDANCE
            )
            artifact_id = start_podcast(
                nb["nb_id"], base_prompt, env,
                topic_id=nb["topic"]["id"],
            )
            nb["artifact_id"] = artifact_id
            status = f"artifact {artifact_id}" if artifact_id else "FAILED to start"
            print(f"  {'OK' if artifact_id else 'FAIL'}: {nb['topic']['label_en']} -> {status}")
            # Pause between generation starts to avoid NotebookLM rate-limiting
            # (a heavy reviews day can queue a dozen-plus generations).
            time.sleep(25)

    # ── Phase 5: Wait for all podcasts (parallel on Google's side) ────────────
    # Long-format podcasts take longer to render — allow up to 75 minutes.
    wait_for_all_podcasts(nb_infos, env, max_wait=4500)

    # ── Phase 6: Download all MP3s (upload comes AFTER QC, so the gate can hold
    #    flagged episodes as drafts) ─────────────────────────────
    print("\n⬇️  Downloading completed podcasts...")
    for nb in nb_infos:
        if nb.get("podcast_ready") and nb.get("nb_id") and nb.get("artifact_id"):
            nb["podcast_path"] = download_podcast(
                nb["nb_id"], nb["artifact_id"], nb["topic"]["id"], env,
            )

    # ── Phase 7: QC BEFORE publishing (so we can gate) ─────────────────────
    # Gemini judges each downloaded episode → qc-report.md + qc-results.json.
    run_qc(env)
    qc_results = load_qc_results()

    # ── Phase 8: Upload — HOLD flagged episodes as drafts, publish the rest ────
    print("\n⬆️  Uploading (holding QC-flagged episodes as drafts)...")
    held = 0
    for nb in nb_infos:
        if not nb.get("podcast_path"):
            continue
        hold = _qc_should_hold(qc_results.get(nb["topic"]["id"]))
        nb["held"] = hold
        held += 1 if hold else 0
        print(f"  {'⏸️ HOLD' if hold else 'Publishing'} {nb['topic']['label_en']}...")
        nb["podcast_url"] = upload_to_github_release(
            nb["podcast_path"], nb["topic"], env,
            artifact_title=nb.get("artifact_title"), draft=hold,
        )
        print(f"  -> {nb['podcast_url']}")
    if held:
        print(f"\n  ⏸️ {held} episode(s) HELD for your review (draft — not on "
              f"Spotify). Publish/regenerate with scripts/publish_episode.py / "
              f"scripts/regenerate_episode.py.")

    # Manifest (nb_id + prompt per episode) for the regenerate/publish tools,
    # then one commit picks up the QC report + results + manifest.
    save_run_manifest(nb_infos)
    commit_summaries_to_github(env)

    # ── Phase 9: Drive backup + RSS (draft episodes excluded) + notify ──────
    backup_to_drive(env)
    update_rss_feed(env)
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
    import argparse

    parser = argparse.ArgumentParser(
        description="Weekly psychiatry literature review + podcast pipeline.",
    )
    parser.add_argument(
        "--mode",
        choices=["reviews", "spotlights", "all"],
        default="all",
        help=(
            "reviews = weekly clusters only (run on the reviews day); "
            "spotlights = single-paper deep-dives only (run on the spotlights "
            "day); all = both in one run (manual / legacy default)."
        ),
    )
    args = parser.parse_args()
    main(mode=args.mode)
