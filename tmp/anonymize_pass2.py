"""Second pass: clean up Ken/Dan references the first sweep didn't reach.

Targets: notebooks, the QA SQL schema, meeting prep doc, build_ledger,
and the SKILL.md. Also rewrites the two derived QA CSVs to swap
RecordedBy='Ken' -> 'TRPA_analyst'.
"""
import re
from pathlib import Path

ROOT = Path(r"C:/Users/mbindl/Documents/GitHub/Reporting")

# Text files (markdown/notebook/SQL) - do phrase + word-boundary replacements
TEXT_TARGETS = [
    "notebooks/05_qa_reconciliation.ipynb",
    "notebooks/01_corral_vs_xlsx_diff.ipynb",
    "notebooks/02_build_transition_table.ipynb",
    "notebooks/03_transition_table_schema.sql",
    "data/qa_data/meeting_prep_2026-05-04.md",
    "ledger_prototype/build_ledger.ipynb",
    ".claude/skills/trpa-cumulative-accounting/SKILL.md",
]

# CSV data files - only swap the literal 'Ken' value in the RecordedBy column
CSV_TARGETS = [
    "data/qa_data/qa_analyst_only_corrections.csv",
    "data/qa_data/qa_change_events.csv",
]

PHRASES = [
    # Full names (in case any survived)
    ("Kenneth Kasman",        "TRPA analyst"),
    ("Ken Kasman",            "TRPA analyst"),
    ("Dan Segan",             "TRPA leadership"),

    # 05 specific
    ("bridge s06 detections to Ken's QA decisions",
     "bridge s06 detections to the analyst's QA decisions"),
    ("Ken's `CA Changes",           "the analyst's `CA Changes"),
    ("Ken corrected this APN",       "the analyst corrected this APN"),
    ("Ken hasn't addressed",         "the analyst hasn't addressed"),
    ("any APNs Ken corrected",       "any APNs the analyst corrected"),
    ("ken_only_correct",             "analyst_only_correct"),
    ("Ken's events",                 "the analyst's events"),
    ("Load Ken's events",            "Load the analyst's events"),

    # 01 / 02 specific
    ("Ken's `2025 Transactions",     "the analyst's `2025 Transactions"),
    ("category 3 (Ken unique)",      "category 3 (analyst unique)"),
    ("how sparse Ken's XLSX",        "how sparse the analyst's XLSX"),

    # 03 SQL
    ("Ken's XLSX-unique",            "the analyst's XLSX-unique"),
    ("Reviewers: TRPA dev team + Ken + Dan", "Reviewers: TRPA dev team + analyst + leadership"),
    ("Ken's unique contribution",    "analyst's unique contribution"),
    ("Ken's internal tracker",       "analyst's internal tracker"),

    # build_ledger
    ("until Ken confirms",           "until the analyst confirms"),

    # SKILL.md
    ("Ken's spreadsheets",           "the analyst's spreadsheets"),
]

WORD_REPL = [
    (re.compile(r"\bKen\b"), "the analyst"),
    (re.compile(r"\bDan\b"), "leadership"),
]


def fix_text_file(p: Path) -> int:
    text = p.read_text(encoding="utf-8")
    before = text
    n = 0
    for old, new in PHRASES:
        c = text.count(old)
        if c:
            text = text.replace(old, new)
            n += c
    for pat, new in WORD_REPL:
        text, k = pat.subn(new, text)
        n += k
    if text != before:
        p.write_text(text, encoding="utf-8")
    return n


def fix_csv_recordedby(p: Path) -> int:
    """Swap the RecordedBy='Ken' column value to 'TRPA_analyst'.

    The CSVs have the column ordered such that 'Ken' appears between two
    commas in the RecordedBy slot. Safer to do an exact-token replace.
    """
    text = p.read_text(encoding="utf-8")
    before = text
    # Field-bounded replacement: ",Ken," -> ",TRPA_analyst,"
    text = text.replace(",Ken,", ",TRPA_analyst,")
    if text != before:
        p.write_text(text, encoding="utf-8")
        return before.count(",Ken,")
    return 0


def main():
    total = 0
    for rel in TEXT_TARGETS:
        p = ROOT / rel
        if not p.is_file():
            print(f"  MISSING {rel}")
            continue
        n = fix_text_file(p)
        print(f"  {rel}: {n}")
        total += n
    for rel in CSV_TARGETS:
        p = ROOT / rel
        if not p.is_file():
            print(f"  MISSING {rel}")
            continue
        n = fix_csv_recordedby(p)
        print(f"  {rel}: {n} RecordedBy values swapped")
        total += n
    print(f"Total: {total}")

    # Verify no residual hits in active text files
    print()
    print("Residual check across text targets:")
    for rel in TEXT_TARGETS:
        p = ROOT / rel
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        ken = len(re.findall(r"\bKen\b", text))
        dan = len(re.findall(r"\bDan\b", text))
        if ken or dan:
            print(f"  {rel}: Ken={ken}, Dan={dan}")


if __name__ == "__main__":
    main()
