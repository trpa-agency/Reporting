"""Apply the same anonymization to the erd/*.html rendered docs that we
already applied to the source erd/*.md."""
import re
from pathlib import Path

ROOT = Path(r"C:/Users/mbindl/Documents/GitHub/Reporting/erd")

# Same replacement table as tmp/anonymize_names.py (subset that matters for
# the erd docs)
PATH_REPLACEMENTS = [
    ("data/from_ken/",   "data/from_analyst/"),
    ("data\\from_ken\\", "data\\from_analyst\\"),
    ("from_ken/",        "from_analyst/"),
    ("from_ken\\",       "from_analyst\\"),
    ("/from_ken",        "/from_analyst"),
]

PHRASES = [
    ("Ken Kasman",          "TRPA analyst"),
    ("Dan Segan",           "TRPA leadership"),
    ("kkasman@trpa.gov",    ""),
    ("dsegan@trpa.gov",     ""),
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
    ("Ken sent",            "The analyst sent"),
    ("Ken delivered",       "The analyst delivered"),
    ("Ken received",        "The analyst received"),
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
    ("Ken and Dan",         "TRPA leadership"),
    ("Ken & Dan",           "TRPA leadership"),
    ("Ken, Dan",            "TRPA leadership"),
    ("Dan and Ken",         "TRPA leadership"),
    ("Ken/Dan",             "TRPA leadership"),
    ("- see Ken",           "- see TRPA analyst"),
    ("(Ken)",               "(TRPA)"),
    ("(Dan)",               "(TRPA)"),
    ("Compiled by Ken",     "Compiled by TRPA"),
    ("compiled by Ken",     "compiled by TRPA"),
    ("Ken says",            "the analyst says"),
    ("Ken notes",           "the analyst notes"),
    ("Ken flagged",         "the analyst flagged"),
]

WORDS = [
    (re.compile(r"\bKen\b"), "the analyst"),
    (re.compile(r"\bDan\b"), "leadership"),
]

total = 0
for p in sorted(ROOT.glob("*.html")):
    text = p.read_text(encoding="utf-8")
    before = text
    n = 0
    for old, new in PATH_REPLACEMENTS:
        c = text.count(old); text = text.replace(old, new); n += c
    for old, new in PHRASES:
        c = text.count(old); text = text.replace(old, new); n += c
    for pat, new in WORDS:
        text, k = pat.subn(new, text); n += k
    if text != before:
        p.write_text(text, encoding="utf-8")
        print(f"  {p.name}: {n}")
        total += n
print(f"Total: {total}")
