"""Final scan: report any residual Ken/Dan/Kasman/Segan/from_ken hits
across live (non-archive) files."""
import re
from pathlib import Path

ROOT = Path(r"C:/Users/mbindl/Documents/GitHub/Reporting")
SKIP_DIRS = ("_archive", ".claude/worktrees", "tmp", "outputs", ".git")
SKIP_EXTS = {".xlsx", ".pdf", ".png", ".jpg", ".jpeg", ".gif",
             ".docx", ".pptx", ".zip", ".lock", ".exe", ".dll"}

ken_re   = re.compile(r"\bKen\b")
dan_re   = re.compile(r"\bDan\b")
name_re  = re.compile(r"Kasman|Segan")
path_re  = re.compile(r"from_ken|fromKen|for_ken|qa_ken")

remaining: dict[str, dict] = {}

for p in ROOT.rglob("*"):
    if not p.is_file():
        continue
    rel = p.relative_to(ROOT).as_posix()
    if any(s in rel for s in SKIP_DIRS):
        continue
    if p.suffix.lower() in SKIP_EXTS:
        continue
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        continue
    counts = {
        "Ken":    len(ken_re.findall(text)),
        "Dan":    len(dan_re.findall(text)),
        "Names":  len(name_re.findall(text)),
        "Paths":  len(path_re.findall(text)),
    }
    if any(counts.values()):
        remaining[rel] = counts

print(f"Files with residual hits: {len(remaining)}")
for rel, c in sorted(remaining.items()):
    print(f"  {rel}: {c}")
