"""Remove references to specific TRPA staff (Ken Kasman, Dan Segan) from
all active project files. Replaces with neutral attribution (e.g. "the
analyst", "TRPA leadership", or just removes the attribution where it
doesn't change meaning).

Scope:
  html/*.html
  html/*.md
  erd/*.md             (.html files are regenerated)
  *.md (repo root)
  data/qa_data/*.md
  parcel_development_history_etl/**/*.{py,md}
  notebooks/*.md
  ledger_prototype/*.md
  resources/*.md
  *.py (top-level)

Skip:
  _archive/**
  .claude/skills/**
  .claude/worktrees/**
  tmp/**
  outputs/**
  data/qa_data/*.xlsx and other binary inputs

Also rewrites the path token `from_ken` -> `from_analyst` everywhere in
code/docs so the directory can be git-mv'd to `data/from_analyst/`.

Order matters: most specific phrases first so the catch-all word-boundary
replacement at the end doesn't garble them.
"""
import re
import sys
from pathlib import Path

ROOT = Path(r"C:/Users/mbindl/Documents/GitHub/Reporting")

# Files to process - glob patterns relative to ROOT
INCLUDE_GLOBS = [
    "*.md",
    "*.py",
    "CLAUDE.md",
    "README.md",
    "html/*.html",
    "html/*.md",
    "erd/*.md",
    "data/qa_data/*.md",
    "ledger_prototype/*.md",
    "notebooks/*.md",
    "resources/*.md",
    "parcel_development_history_etl/**/*.py",
    "parcel_development_history_etl/**/*.md",
]

SKIP_SUBSTR = [
    "_archive",
    ".claude/skills",
    ".claude/worktrees",
    "/tmp/",
    "/outputs/",
]

# Path token first (preserve directory references that we'll git-mv later)
PATH_REPLACEMENTS = [
    ("data/from_ken/", "data/from_analyst/"),
    ("data\\from_ken\\", "data\\from_analyst\\"),
    ("from_ken/",      "from_analyst/"),
    ("from_ken\\",     "from_analyst\\"),
    ("/from_ken",      "/from_analyst"),  # bare path token
]

# Specific phrases (run BEFORE the word-boundary catch-all)
PHRASE_REPLACEMENTS = [
    # Full names
    ("Ken Kasman",          "TRPA analyst"),
    ("Dan Segan",           "TRPA leadership"),
    ("kkasman@trpa.gov",    ""),
    ("dsegan@trpa.gov",     ""),
    ("masonbindl@gmail.com", "masonbindl@gmail.com"),  # keep (Mason's own email)

    # Possessives + role tags
    ("Ken's",               "the analyst's"),
    ("Ken-curated",         "manually curated"),
    ("Ken-XLSX",            "analyst-XLSX"),
    ("Ken (analyst)",       "the analyst"),
    ("Ken correction",      "manual correction"),
    ("Hi Ken et al.",       "(prior email exchange)"),
    ("Hi Ken,",             ""),
    ("Per Ken",             "Per the analyst"),
    ("per Ken",             "per the analyst"),
    ("From Ken",            "From the analyst"),
    ("from Ken",            "from the analyst"),
    ("by Ken",              "by the analyst"),
    ("Re-run when Ken",     "Re-run when the analyst"),
    ("when Ken sends",      "when the analyst sends"),
    ("Ken's wording",       "the analyst's wording"),
    ("Ken's manual",        "the manual"),
    ("Ken sent",            "The analyst sent"),
    ("Ken delivered",       "The analyst delivered"),
    ("Ken received",        "The analyst received"),

    # Dan attributions
    ("Dan's framing",       "the framing"),
    ("Dan's three",         "the three"),
    ("Dan's four",          "the four"),
    ("Dan's tracks",        "the tracks"),
    ("Dan's #",             "track #"),
    ("Per Dan",             "Per the agency"),
    ("per Dan",             "per the agency"),
    ("Per Dan's",           "Per the"),
    ("per Dan's",           "per the"),
    ("Dan's email",         "the email"),
    ("Dan asked",           "leadership asked"),
    ("Dan said",            "leadership said"),
    ("Dan provided",        "leadership provided"),
    ("from Dan",            "from leadership"),
    ("by Dan",              "by leadership"),

    # Both
    ("Ken and Dan",         "TRPA leadership"),
    ("Ken & Dan",           "TRPA leadership"),
    ("Ken, Dan",            "TRPA leadership"),
    ("Dan and Ken",         "TRPA leadership"),
    ("Ken/Dan",             "TRPA leadership"),

    # Specific known phrases that come up
    ("— see Ken",      "(see TRPA analyst"),
    ("- see Ken",           "- see TRPA analyst"),
    ("(Ken)",               "(TRPA)"),
    ("(Dan)",               "(TRPA)"),

    # Compiled-by attribution
    ("Compiled by Ken",     "Compiled by TRPA"),
    ("compiled by Ken",     "compiled by TRPA"),
]

# Word-boundary catch-all - run LAST, after all phrase substitutions
# Use regex to handle word boundaries cleanly
WORD_REPLACEMENTS = [
    (r"\bKen\b",  "the analyst"),
    (r"\bDan\b",  "leadership"),
]


def should_skip(p: Path) -> bool:
    s = str(p).replace("\\", "/")
    return any(skip in s for skip in SKIP_SUBSTR)


def main() -> None:
    seen: set[Path] = set()
    files: list[Path] = []
    for pat in INCLUDE_GLOBS:
        for p in ROOT.glob(pat):
            if p.is_file() and p not in seen and not should_skip(p):
                seen.add(p); files.append(p)

    print(f"Scanning {len(files)} files...")
    print("=" * 70)
    total_replacements = 0
    files_touched = 0

    for p in sorted(files):
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError) as e:
            print(f"  skip {p.relative_to(ROOT)}: {e}")
            continue

        before = text
        n_replaced = 0

        # 1. Path tokens
        for old, new in PATH_REPLACEMENTS:
            count = text.count(old)
            if count:
                text = text.replace(old, new)
                n_replaced += count

        # 2. Phrase replacements
        for old, new in PHRASE_REPLACEMENTS:
            count = text.count(old)
            if count:
                text = text.replace(old, new)
                n_replaced += count

        # 3. Word-boundary catch-all (regex)
        for pat, new in WORD_REPLACEMENTS:
            text, n = re.subn(pat, new, text)
            n_replaced += n

        if text != before:
            print(f"  {p.relative_to(ROOT)}: {n_replaced} replacements")
            p.write_text(text, encoding="utf-8")
            files_touched += 1
            total_replacements += n_replaced

    print("=" * 70)
    print(f"Done: {files_touched} files modified, {total_replacements} replacements.")


if __name__ == "__main__":
    main()
