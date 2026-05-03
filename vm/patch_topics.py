#!/usr/bin/env python3
"""Replace old 5-topic TOPICS list in weekly_review.py with new 10-cluster version.
Run from repo root: python vm/patch_topics.py
"""
from pathlib import Path

ROOT   = Path(__file__).resolve().parent.parent
target = ROOT / "scripts" / "weekly_review.py"

lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
print(f"Read {len(lines)} lines from {target.name}")

# Sanity checks
assert "TOPICS = [" in lines[183], f"Line 184 mismatch: {lines[183]!r}"
assert lines[336].strip() == "]",  f"Line 337 mismatch: {lines[336]!r}"

# ── New 10-cluster TOPICS ────────────────────────────────────────────────────
# This string is written verbatim into weekly_review.py (valid UTF-8 Python).
NEW_TOPICS = (
"""TOPICS = [
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
            "צור דיון מעמיק ומרתק על הממצאים המשמעותיים ביותר של השבוע "
            "בפסיכיאטריה של הילד והמתבגר. דגש על רלוונטיות קלינית, "
            "גישות טיפוליות חדשות, ומשמעות הממצאים למתמחה בפסיכיאטריה."
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
            "JAMA Pediatr",                          # IF~27 — mental-health filtered via broad
        ],
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
            "צור דיון על המאמרים בעלי ההשפעה הגבוהה ביותר מהשבוע הנוגעים לילדים ומתבגרים "
            "מכתבי עת מובילים. דגש על חשיבות הממצאים, שינויים פוטנציאליים בפרקטיקה, "
            "ומשמעות עבור פסיכיאטריית ילד ומתבגר."
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
            "צור דיון על הממצאים הקליניים המשמעותיים בפסיכיאטריה הכללית של השבוע. "
            "דגש על מה מהפסיכיאטריה הכללית רלוונטי לטיפול בילדים ומתבגרים, "
            "ומה המתמחה יכול ללמוד מהפסיכיאטריה הכללית."
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
            "צור דיון על המחקר הביולוגי והפסיכופרמקולוגי המשמעותי ביותר של השבוע. "
            "דגש על מנגנונים ביולוגיים, גנטיקה, וטיפולים תרופתיים — "
            "מה המשמעות לפסיכיאטריית ילד ומתבגר?"
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
            "צור דיון על המחקרים המשמעותיים בתחום התפתחות הילד של השבוע. "
            "דגש על השלכות לפסיכיאטריה של הילד, חשיבות ממצאים "
            "להתפתחות תקינה ופתולוגית, התקשרות, והתערבות מוקדמת."
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
        ],
        "broad": [
            '"Nature Neuroscience"[Journal] AND ("psychiatry"[Title/Abstract] OR "depression"[Title/Abstract] OR "schizophrenia"[Title/Abstract] OR "autism"[Title/Abstract] OR "development"[Title/Abstract])',
            '"brain development"[MeSH] AND ("child"[MeSH] OR "adolescent"[MeSH])',
            '"prefrontal cortex"[MeSH] AND ("adolescent"[MeSH] OR "development"[Title/Abstract])',
            '"neuroplasticity"[MeSH] AND ("psychiatric disorders"[Title/Abstract] OR "mental health"[Title/Abstract])',
            '"stress"[MeSH] AND ("brain"[Title/Abstract] OR "neurobiology"[Title/Abstract]) AND ("child"[MeSH] OR "adolescent"[MeSH])',
        ],
        "max_articles": 10,
        "podcast_prompt": (
            "צור דיון על ממצאי מדעי המוח המשמעותיים ביותר של השבוע. "
            "דגש על השלכות לפסיכיאטריה של הילד ולהבנת המנגנונים העצביים "
            "של הפרעות פסיכיאטריות."
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
        "broad": [
            '"Int J Psychoanal"[Journal] OR "International Journal of Psychoanalysis"[Journal]',
            '"psychotherapy"[MeSH] AND ("randomized controlled trial"[pt] OR "meta-analysis"[pt])',
            '"cognitive behavioral therapy"[Title/Abstract] AND ("randomized controlled trial"[pt] OR "meta-analysis"[pt])',
            '"dialectical behavior therapy"[Title/Abstract]',
            '"parent training"[Title/Abstract] AND ("child"[MeSH] OR "adolescent"[MeSH])',
            '"trauma-focused"[Title/Abstract] AND ("child"[MeSH] OR "adolescent"[MeSH])',
        ],
        "max_articles": 10,
        "podcast_prompt": (
            "צור דיון על הממצאים המשמעותיים בפסיכותרפיה ובהתערבויות של השבוע. "
            "כלול התערבויות לילדים, מתבגרים ומבוגרים. "
            "דגש על יישום קליני ועדויות אמפיריות."
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
        "broad": [
            '"learning"[MeSH] AND ("behavior"[Title/Abstract] OR "conditioning"[Title/Abstract]) AND ("child"[MeSH] OR "adolescent"[MeSH] OR "psychiatric"[Title/Abstract])',
            '"reward"[Title/Abstract] AND ("adolescent"[MeSH] OR "development"[Title/Abstract]) AND ("brain"[Title/Abstract] OR "behavior"[Title/Abstract])',
            '"social cognition"[Title/Abstract] AND ("autism"[MeSH] OR "schizophrenia"[MeSH] OR "child"[MeSH])',
        ],
        "max_articles": 10,
        "podcast_prompt": (
            "צור דיון על ממצאי מדעי ההתנהגות המשמעותיים ביותר של השבוע. "
            "דגש על השלכות לפסיכיאטריה ולהבנת התנהגות אנושית — "
            "למידה, חיזוק, קוגניציה חברתית."
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
        "broad": [
            '"executive function"[Title/Abstract] AND ("child"[MeSH] OR "adolescent"[MeSH])',
            '"working memory"[Title/Abstract] AND ("child"[MeSH] OR "adolescent"[MeSH] OR "development"[Title/Abstract])',
            '"attention"[MeSH] AND "development"[Title/Abstract] AND ("child"[MeSH] OR "infant"[MeSH])',
            '"language development"[MeSH]',
        ],
        "max_articles": 10,
        "podcast_prompt": (
            "צור דיון על הממצאים המשמעותיים בתחום הקוגניציה של השבוע. "
            "דגש על השלכות להתפתחות קוגניטיבית, להפרעות קוגניטיביות, "
            "ולפסיכיאטריה של הילד."
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
            "צור דיון על מאמרים מגוונים ומעניינים בתחום ילדים ומתבגרים מהשבוע. "
            "אלו מאמרים מכתבי עת שונים שלא כוסו בסקירות האחרות. "
            "דגש על ממצאים מעניינים, מפתיעים, או בעלי חשיבות קלינית."
        ),
    },
]
"""
)

# ── Patch the file ────────────────────────────────────────────────────────────
before = lines[:183]          # lines 1-183 (0-indexed 0-182)
after  = lines[337:]          # lines 338+ (0-indexed 337+)

new_content = "".join(before) + NEW_TOPICS + "".join(after)

target.write_text(new_content, encoding="utf-8")
new_line_count = len(new_content.splitlines())
print(f"Wrote {new_line_count} lines to {target.name}")
print("TOPICS replacement complete.")
