"""One-off: rewrite notebook 04 to remove `from_ken/` paths and Ken attributions."""
import re
from pathlib import Path

p = Path(r"C:/Users/mbindl/Documents/GitHub/Reporting/notebooks/04_load_ca_changes.ipynb")
text = p.read_text(encoding="utf-8")
before = text

# JSON-escaped Windows path: "\\from_ken\\" -> "\\data\\from_analyst\\"
text = text.replace("\\\\from_ken\\\\", "\\\\data\\\\from_analyst\\\\")

# Python Path() expression: REPO_ROOT / 'from_ken' / 'X' -> REPO_ROOT / 'data' / 'from_analyst' / 'X'
text = text.replace("REPO_ROOT / 'from_ken' /", "REPO_ROOT / 'data' / 'from_analyst' /")

# Markdown / inline references
text = text.replace("committed copy in from_ken/", "committed copy in data/from_analyst/")
text = text.replace("from_ken/FINAL RES SUMMARY", "data/from_analyst/FINAL RES SUMMARY")

# Specific Ken phrases
SPECIFIC = [
    ("Load Ken's CA Changes",   "Load the analyst's CA Changes"),
    ("Ken's CA Changes",         "the analyst's CA Changes"),
    ("Ken's master record",      "the analyst's master record"),
    ("Ken's data is residential","The analyst's data is residential"),
    ("Ken's wording varies",     "the analyst's wording varies"),
    ("Ken's Sheet1 wording",     "the analyst's Sheet1 wording"),
    ("Ken's XLSX carries",       "the analyst's XLSX carries"),
    ("Ken updates the XLSX",     "the analyst updates the XLSX"),
    ("'RecordedBy':         'Ken'", "'RecordedBy':         'TRPA_analyst'"),
]
for old, new in SPECIFIC:
    text = text.replace(old, new)

# Word-boundary catch-all
text = re.sub(r"\bKen\b", "the analyst", text)
text = re.sub(r"\bDan\b", "leadership",   text)

if text != before:
    p.write_text(text, encoding="utf-8")
    diff_chars = len(text) - len(before)
    print(f"Updated notebook 04 ({diff_chars:+d} chars)")
else:
    print("No changes")

# Verify
remaining_from_ken = text.count("from_ken")
remaining_Ken      = len(re.findall(r"\bKen\b", text))
remaining_Dan      = len(re.findall(r"\bDan\b", text))
print(f"Residual: from_ken={remaining_from_ken}, Ken={remaining_Ken}, Dan={remaining_Dan}")
