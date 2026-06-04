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
        "max_articles": 12,
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
        "max_articles": 10,
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
        "max_articles": 12,
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
        "max_articles": 12,
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


# ── Shared tone / structure guidance — appended to every podcast prompt ──────
# Lives separately so we can edit once and have it apply to all clusters
# (regular + spotlight). Written in English for instruction fidelity; the
# Hebrew disclaimer is given verbatim because that's what listeners hear.
TONE_GUIDANCE = (
    "\n\n"
    "========================================================================\n"
    "MANDATORY OPENING — the FIRST thing said in the podcast, verbatim:\n"
    "========================================================================\n"
    "Open with this exact Hebrew disclaimer, read calmly and clearly:\n"
    "'הפודקאסט הבא נוצר באופן אוטומטי באמצעות בינה מלאכותית. התוכן עלול להכיל "
    "אי-דיוקים, פרשנויות שגויות או המצאות. אין להסתמך עליו לקבלת החלטות "
    "קליניות. חובה לבדוק כל פרט באופן עצמאי מול המקור המקורי.'\n"
    "\n"
    "========================================================================\n"
    "OPENING NARRATIVE (after the disclaimer):\n"
    "========================================================================\n"
    "The podcast SHOULD open with a meaningful philosophical or clinical "
    "framing — roughly 1-3 minutes — that creates a narrative thread for the "
    "episode. A thoughtful opening adds real value: it tells the resident what "
    "to listen for and gives them a lens through which to think about the "
    "week's papers. Do NOT skip the framing — a good one is wanted.\n"
    "\n"
    "Good framings include (any one is enough):\n"
    "  • A tension between two specific papers in this week's set, and the\n"
    "    question they raise together.\n"
    "  • A clinically actionable question raised by the week's findings —\n"
    "    e.g. 'if finding X holds up, what should we be doing differently\n"
    "    when we see Y in clinic?'\n"
    "  • Points to think about (נקודות למחשבה) — how a paper from a\n"
    "    non-clinical field (basic neuroscience, cognition, behavioral\n"
    "    science) bears on child / adolescent psychiatric practice.\n"
    "  • A methodological or conceptual thread that recurs across several\n"
    "    of this week's papers.\n"
    "\n"
    "The framing MUST be:\n"
    "  • Anchored in actual papers from THIS WEEK's source material — name\n"
    "    a paper, a finding, or a specific question. Generic philosophical\n"
    "    musing without a concrete hook does not work.\n"
    "  • Genuinely fresh — DIFFERENT from how previous episodes opened. The\n"
    "    same framing template every week is the failure mode to avoid.\n"
    "\n"
    "The framing MUST NOT be:\n"
    "  • An explanation of what child psychiatry is or what child\n"
    "    psychiatrists do. The audience is a child psychiatry resident —\n"
    "    they know.\n"
    "  • The 'fracture line vs fuzzy psychiatry' framing, or any variant of\n"
    "    'general medicine has clear boundaries, psychiatry doesn't'. This\n"
    "    pattern has been overused and is explicitly banned.\n"
    "  • Boilerplate about 'the literature is vast', 'the field is complex',\n"
    "    or 'staying current is hard'.\n"
    "  • Any opening that could equally well fit any other week's episode —\n"
    "    if the same words could open last week's podcast, the framing is\n"
    "    too generic.\n"
    "\n"
    "In short: a philosophical / reflective opening is encouraged. What is\n"
    "forbidden is recycling the same generic template week after week, or\n"
    "explaining basics the audience already knows. If you anchor every\n"
    "framing in this week's actual papers, variety follows automatically.\n"
    "\n"
    "========================================================================\n"
    "JOURNAL ATTRIBUTION (MANDATORY, every paper):\n"
    "========================================================================\n"
    "For EVERY paper you discuss, state the journal name aloud — e.g. "
    "'המאמר פורסם ב-JAMA Psychiatry' or 'מאמר ב-Lancet Psychiatry'. "
    "Non-negotiable. Listeners need to know where each finding comes from.\n"
    "\n"
    "========================================================================\n"
    "STUDY TYPE (MANDATORY, every paper):\n"
    "========================================================================\n"
    "When you START discussing a paper, also state its STUDY TYPE — מטה-אנליזה, "
    "סקירה שיטתית, RCT, מחקר עוקבה, מחקר תצפיתי, תיאור מקרה, מאמר סקירה, "
    "מאמר מערכת, etc. The source material includes a 'סוג מחקר:' field per "
    "paper — use it verbatim, do NOT guess. When the field says 'מאמר מחקרי' "
    "(the generic fallback), try to identify a more specific design from the "
    "abstract (e.g., 'מחקר חתך', 'מחקר עוקבה פרוספקטיבי') and say so. "
    "Study type matters for how listeners weigh the evidence — an RCT carries "
    "different weight than a case report.\n"
    "\n"
    "========================================================================\n"
    "DEPTH AND COVERAGE:\n"
    "========================================================================\n"
    "Cover EVERY paper in the source material — do not skip papers because they "
    "seem less interesting. Spend 2-4 minutes per paper: methods, findings with "
    "effect sizes, limitations, and clinical implications. The podcast should be "
    "as LONG and EXHAUSTIVE as possible. Listeners want depth, not a teaser. "
    "Do not summarize multiple papers in one sentence — each gets its own time.\n"
    "\n"
    "========================================================================\n"
    "CONTINUITY WITH PREVIOUS WEEK ('משבוע שעבר' section):\n"
    "========================================================================\n"
    "The source material may end with a section titled 'משבוע שעבר — לקונטקסט "
    "בלבד'. The papers listed there were COVERED IN LAST WEEK'S PODCAST — they "
    "are NOT new content this week.\n"
    "  • Do NOT re-summarize those papers as if they were new.\n"
    "  • Do NOT spend airtime on them on their own merit.\n"
    "  • DO use them as context: if a paper THIS WEEK is by the same authors, "
    "extends the same line of work, contradicts last week's finding, or "
    "addresses the same clinical question — name the connection briefly "
    "('כפי שראינו בשבוע שעבר, Smith וחבריו פרסמו ב-X; השבוע...'). This makes "
    "the podcast feel like an ongoing series rather than 10 disconnected episodes.\n"
    "  • If there is no meaningful connection — ignore the section entirely.\n"
    "\n"
    "========================================================================\n"
    "TONE:\n"
    "========================================================================\n"
    "Professional, balanced, precise. AVOID superlatives ('groundbreaking', "
    "'paradigm-shifting', 'stunning', 'revolutionary', 'changes everything we "
    "knew'). Describe findings in measured language. Always note methodological "
    "limitations and effect sizes. The difference between 'effective' and "
    "'highly effective' matters — do not inflate. Maintain the same balanced "
    "tone when speaking Hebrew.\n"
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


def search_topic(topic: dict) -> list[dict]:
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
    """
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

    # 1. Journal-targeted searches (high priority)
    for journal in topic.get("journals", []):
        q = f'"{journal}"[Journal]'
        if journal_filter:
            q = f'{q} AND {journal_filter}'
        ids = _esearch(q, retmax=6)
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

# Dedicated psychiatry journals — ANY review in these counts as psychiatric.
SPOTLIGHT_JOURNALS_PSYCHIATRY = [
    "JAMA Psychiatry", "Lancet Psychiatry", "World Psychiatry",
    "Am J Psychiatry", "Mol Psychiatry", "Biol Psychiatry",
    "Neuropsychopharmacology", "J Am Acad Child Adolesc Psychiatry",
    "Lancet Child Adolesc Health",
]

# Generalist top journals — reviews here only count when they are actually
# about mental health / psychiatry (filtered with SPOTLIGHT_PSY_FILTER).
# Without this filter, BMJ / Lancet / JAMA reviews on orthopedics, calcium
# supplementation, ovarian syndrome etc. would flood the spotlight list.
SPOTLIGHT_JOURNALS_GENERAL = [
    "JAMA", "JAMA Pediatr",
    "N Engl J Med", "Lancet", "BMJ", "Nature Medicine",
    "Nature Reviews Neuroscience", "Nature Reviews Disease Primers",
]

# TITLE-only filter applied to reviews from SPOTLIGHT_JOURNALS_GENERAL.
# Using [Title] (not [Title/Abstract]) is intentional: in generalist journals
# papers on non-psychiatric topics frequently mention "mental health" or
# "depression" in their abstract as a comorbidity, even when the paper is
# really about kidney disease, oncology, etc. Requiring the psychiatric
# term in the TITLE keeps only papers whose primary subject is psychiatry.
SPOTLIGHT_PSY_FILTER = (
    '("psychiat*"[Title] OR "mental disorder*"[Title] OR "mental health"[Title] '
    'OR "mental illness"[Title] OR "psychopathology"[Title] '
    'OR "depress*"[Title] OR "anxiety"[Title] OR "schizophrenia"[Title] '
    'OR "bipolar"[Title] OR "ADHD"[Title] OR "attention-deficit"[Title] '
    'OR "autism"[Title] OR "OCD"[Title] OR "obsessive-compulsive"[Title] '
    'OR "PTSD"[Title] OR "post-traumatic stress"[Title] '
    'OR "psychosis"[Title] OR "psychotic"[Title] OR "suicid*"[Title] '
    'OR "antipsychotic*"[Title] OR "antidepressant*"[Title] '
    'OR "psychotropic"[Title] OR "psychotherapy"[Title] '
    'OR "neurodevelopmental"[Title] OR "eating disorder*"[Title] '
    'OR "substance use"[Title] OR "addict*"[Title] '
    'OR "personality disorder*"[Title] OR "child psychiatry"[Title] '
    'OR "adolescent psychiatry"[Title] OR "self-harm"[Title] '
    'OR "self-injury"[Title] OR "anorexia"[Title] OR "bulimia"[Title])'
)

# Cap on number of spotlight podcasts per week — keeps the output manageable
# and the most-important reviews surface to the top via sort-by-IF.
MAX_SPOTLIGHT_REVIEWS = 3


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


def find_spotlight_reviews() -> list[dict]:
    """Find recent high-impact REVIEW articles deserving dedicated podcasts.

    Each return value is a topic dict (same shape as entries in TOPICS) with a
    `_forced_articles` field carrying the single article. search_topic() will
    pick this up and skip PubMed.

    Looks back 14 days (broader than the 8-day window used for regular topics)
    so important reviews are not missed if they were published just before the
    weekly run.
    """
    print("\n🔍 Searching for spotlight review articles (last 14 days)...")

    pub_type_filter = (
        '("review"[Publication Type] OR "systematic review"[Publication Type] '
        'OR "meta-analysis"[Publication Type])'
    )
    psy_journals = "(" + " OR ".join(
        f'"{j}"[Journal]' for j in SPOTLIGHT_JOURNALS_PSYCHIATRY
    ) + ")"
    gen_journals = "(" + " OR ".join(
        f'"{j}"[Journal]' for j in SPOTLIGHT_JOURNALS_GENERAL
    ) + ")"
    author_clause = "(" + " OR ".join(
        f'"{a}"[Author]' for a in SPOTLIGHT_HIGH_SIGNAL_AUTHORS
    ) + ")"

    queries = [
        # 1. Reviews in dedicated psychiatry journals — every review counts.
        f'{pub_type_filter} AND {psy_journals}',
        # 2. Reviews in generalist medical journals — MUST also be about
        #    psychiatry / mental health, otherwise we get calcium-supplement
        #    and oncology reviews crowding out actual psychiatric content.
        f'{pub_type_filter} AND {gen_journals} AND {SPOTLIGHT_PSY_FILTER}',
        # 3. Reviews by named high-signal psychiatry/neuroscience authors —
        #    these authors write almost exclusively in psychiatry, so no
        #    extra topic filter needed.
        f'{pub_type_filter} AND {author_clause}',
    ]

    seen: dict[str, bool] = {}
    for q in queries:
        ids = _esearch_reldate(q, reldate=14, retmax=12)
        for p in ids:
            if p not in seen:
                seen[p] = True

    if not seen:
        print("  No spotlight reviews this week.")
        return []

    articles = _esummary(list(seen.keys()), "Spotlight Review")
    for a in articles:
        a["impact_factor"] = get_journal_if(a["journal"])

    # Keep only those in high-IF journals (>=10). Stahl in JCAP (IF~3.5) still
    # passes through the author route because we keep IF >= 10 OR known author.
    known_authors_lc = {a.lower() for a in SPOTLIGHT_HIGH_SIGNAL_AUTHORS}
    def _has_signal_author(article: dict) -> bool:
        # Check whether any high-signal author name appears in the authors string
        authors_lc = article.get("authors", "").lower()
        return any(name in authors_lc for name in known_authors_lc)

    articles = [
        a for a in articles
        if a["impact_factor"] >= 10 or _has_signal_author(a)
    ]
    articles.sort(key=lambda a: -a["impact_factor"])
    articles = articles[:MAX_SPOTLIGHT_REVIEWS]

    if not articles:
        print("  No spotlight reviews this week (after filtering).")
        return []

    print(f"  Found {len(articles)} spotlight review(s):")
    for a in articles:
        print(f"    • {a['journal']} (IF {a['impact_factor']:.1f}): {a['title'][:70]}")

    spotlight_topics: list[dict] = []
    for a in articles:
        pmid = a["pmid"]
        # Short label — notebook titles have length limits in NotebookLM
        title_short = a["title"][:50] + ("…" if len(a["title"]) > 50 else "")
        first_author = a["authors"].split(",")[0].replace(" et al.", "").strip()
        spotlight_topics.append({
            "id":       f"spotlight_{pmid}",
            "label_en": f"Spotlight: {first_author} — {title_short}",
            "label_he": f"מאמר סקירה: {first_author} — {title_short}",
            "journals": [],
            "broad":    [],
            "max_articles": 1,
            "_forced_articles": [a],
            "podcast_prompt": (
                f"This is a DEDICATED, single-paper deep-dive podcast on one "
                f"high-impact review article:\n"
                f"  Title: \"{a['title']}\"\n"
                f"  Authors: {a['authors']}\n"
                f"  Journal: {a['journal']} (IF: {a['impact_factor']:.1f})\n"
                f"  Type: review / systematic review / meta-analysis\n\n"
                "Treat this as a LONG, comprehensive single-paper podcast — "
                "every section of the review deserves real discussion. "
                "Cover: (a) the clinical or scientific question motivating the "
                "review, (b) the methodology (for a systematic review: search "
                "strategy, inclusion criteria, risk-of-bias assessment, "
                "heterogeneity I², publication bias; for a narrative review: "
                "the author's framework and how they structure the evidence), "
                "(c) the synthesis of evidence with effect sizes and confidence "
                "intervals where given, (d) controversies and counter-arguments, "
                "(e) limitations of the evidence base, (f) clinical implications "
                "for everyday practice. "
                "If this is a Stahl-style psychopharmacology review: name the "
                "receptors, mechanisms, pharmacokinetics, and clinical pearls "
                "carefully — that level of mechanistic detail is what makes "
                "Stahl reviews valuable. "
                "For a child / adolescent psychiatry resident: emphasize what "
                "should change in clinical practice, what remains uncertain, "
                "what to do differently tomorrow morning. "
                "Generate the podcast entirely in Hebrew."
            ),
        })
    return spotlight_topics


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
        if if_val > 0:
            journal_str = f"{if_badge(if_val)} {a['journal']} *(IF: {if_val:.1f})*"
        else:
            journal_str = f"\U0001f4c4 {a['journal']}"
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


def start_podcast(nb_id: str, prompt: str, env: dict) -> str | None:
    """Switch to notebook and fire off podcast generation.
    Returns artifact_id or None. Does NOT wait for completion."""
    subprocess.run(
        ["notebooklm", "use", nb_id],
        capture_output=True, env=env, timeout=30,
    )
    full_prompt = prompt + TONE_GUIDANCE
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
) -> str | None:
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

    subprocess.run([
        "gh", "release", "create", tag, podcast_path,
        "--title", f"\U0001f4da {display_title} \u2014 {DATE_STR}",
        "--notes",
            f"{topic['label_en']} weekly literature review {DATE_STR}\n\n"
            f"Cluster: {topic['label_he']}\n\n"
            f"*Generated automatically*",
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


# ── Auto-split crowded topics into Part 1 / Part 2 / ... ─────────────────────
# If a cluster collected too many articles for one comfortable listen, split
# it into multiple parts. Each part becomes its own notebook + podcast +
# GitHub release, with `_part{N}` appended to the topic_id and "(חלק N/M)"
# appended to the Hebrew label. Articles are sorted by Impact Factor
# (descending) and divided round-robin among the parts so each part gets a
# balanced mix of high-IF papers rather than Part 1 hoarding the best.

SPLIT_THRESHOLD = 20   # split topics with more than this many articles
SPLIT_TARGET    = 14   # aim for ~this many articles per part


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

    # Spotlight reviews — each high-impact review gets its own dedicated podcast,
    # in addition to (not instead of) the regular cluster podcasts.
    for stopic in find_spotlight_reviews():
        articles = search_topic(stopic)  # uses _forced_articles internally
        if not articles:
            continue
        all_articles.extend(articles)
        nb_infos.append({
            "topic":         stopic,
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

    # ── Auto-split crowded topics into Part 1 / Part 2 / ... ──────────────────
    nb_infos = auto_split_topics(nb_infos)

    # ── Assign episode numbers (X/Y) within this week's batch ─────────────────
    # Order: regular cluster topics first (in TOPICS order), then spotlight
    # reviews (highest IF first). This is the natural progression a listener
    # would follow. The number shows in the notebook title, the GitHub release
    # title, the ntfy notification, and the RSS feed — so the user can track
    # what they have already listened to.
    total_episodes = len(nb_infos)
    for idx, nb in enumerate(nb_infos, start=1):
        nb["episode_number"] = idx
        nb["episode_total"]  = total_episodes
    print(f"\n📋 This week: {total_episodes} podcast episode(s) to produce.")

    # Fetch text for ALL articles in one pass (PMC full text when available)
    fetch_article_text(all_articles)

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

    # Commit summaries to GitHub regardless of NotebookLM status
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
            artifact_id = start_podcast(nb["nb_id"], nb["topic"]["podcast_prompt"], env)
            nb["artifact_id"] = artifact_id
            status = f"artifact {artifact_id}" if artifact_id else "FAILED to start"
            print(f"  {'OK' if artifact_id else 'FAIL'}: {nb['topic']['label_en']} -> {status}")
            time.sleep(10)   # short pause to avoid rate-limiting

    # ── Phase 5: Wait for all podcasts (parallel on Google's side) ────────────
    # Long-format podcasts take longer to render — allow up to 75 minutes.
    wait_for_all_podcasts(nb_infos, env, max_wait=4500)

    # ── Phase 6: Download + Upload ────────────────────────────────────────────
    print("\n\u2b07\ufe0f  Downloading & uploading completed podcasts...")
    for nb in nb_infos:
        if nb.get("podcast_ready") and nb.get("nb_id") and nb.get("artifact_id"):
            path = download_podcast(nb["nb_id"], nb["artifact_id"], nb["topic"]["id"], env)
            nb["podcast_path"] = path
            if path:
                print(f"  Uploading {nb['topic']['label_en']}...")
                url = upload_to_github_release(
                    path, nb["topic"], env,
                    nb.get("episode_number"), nb.get("episode_total"),
                    artifact_title=nb.get("artifact_title"),
                )
                nb["podcast_url"] = url
                print(f"  -> {url}")

    # ── Phase 7: Drive backup (MP3s) + RSS feed for podcast distribution ────
    backup_to_drive(env)
    update_rss_feed(env)

    # ── Phase 8: Notify ───────────────────────────────────────────────────────
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
