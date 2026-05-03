#!/usr/bin/env python3
"""Apply miscellaneous patches to weekly_review.py:
  1. Prefix notebook titles with [PsychReview] (enables targeted cleanup)
  2. Add cleanup_old_notebooks() function
  3. Call cleanup at start of Phase 2 in main()
Run from repo root: python vm/patch_misc.py
"""
import re
from pathlib import Path

ROOT   = Path(__file__).resolve().parent.parent
target = ROOT / "scripts" / "weekly_review.py"
content = target.read_text(encoding="utf-8")

# ── 1. Prefix notebook title with [PsychReview] ────────────────────────────────
OLD_TITLE = "        title = f\"{nb['topic']['label_he']}"
NEW_TITLE = "        title = f\"[PsychReview] {nb['topic']['label_he']}"
assert OLD_TITLE in content, "Could not find notebook title line — already patched?"
content = content.replace(OLD_TITLE, NEW_TITLE, 1)
print("1. Notebook title prefix applied.")

# ── 2. Add cleanup_old_notebooks() before # ── Main ────────────────────────────
CLEANUP_FUNC = '''
# ── Cleanup old project notebooks ─────────────────────────────────────────────
def cleanup_old_notebooks(env: dict):
    """Delete [PsychReview] project notebooks older than 4 weeks.

    Only notebooks whose title starts with \'[PsychReview]\' are touched —
    personal notebooks are never deleted.
    """
    cutoff = TODAY - timedelta(weeks=4)
    print("\\n\\U0001f5d1\\ufe0f  Cleaning up old [PsychReview] notebooks (older than 4 weeks)...")
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
        # Extract date from end of title: "[PsychReview] ... \\u2014 YYYY-MM-DD"
        m = re.search(r"(\\d{4}-\\d{2}-\\d{2})$", title.strip())
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


'''

MAIN_MARKER = "# ── Main ───────────────────────────────────────────────────────────────────────"
assert MAIN_MARKER in content, "Could not find # ── Main marker"
content = content.replace(MAIN_MARKER, CLEANUP_FUNC + MAIN_MARKER, 1)
print("2. cleanup_old_notebooks() function inserted.")

# ── 3. Add cleanup call at start of Phase 2 ────────────────────────────────────
PHASE2_MARKER = "    # ── Phase 2: Create notebooks "
CLEANUP_CALL = (
    "    # ── Phase 2: Create notebooks "
)
# Insert cleanup call just before Phase 2 comment
OLD_PHASE2 = "    # ── Phase 2: Create notebooks ─────────────────────────────────────────────"
NEW_PHASE2 = (
    "    # ── Clean up old project notebooks (keep last 4 weeks) ─────────────────────\n"
    "    cleanup_old_notebooks(env)\n"
    "\n"
    "    # ── Phase 2: Create notebooks ─────────────────────────────────────────────"
)
assert OLD_PHASE2 in content, "Could not find Phase 2 marker"
content = content.replace(OLD_PHASE2, NEW_PHASE2, 1)
print("3. cleanup_old_notebooks() call inserted before Phase 2.")

# ── 4. Add `import re` at module level (needed by cleanup function) ─────────────
# Check if re is already imported
if "\nimport re\n" not in content and "import re\n" not in content[:500]:
    content = content.replace("import os\n", "import os\nimport re\n", 1)
    print("4. Added `import re` import.")
else:
    print("4. `import re` already present — skipped.")

target.write_text(content, encoding="utf-8")
print(f"\nDone. {target.name} updated successfully.")
