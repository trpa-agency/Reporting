"""Generate meeting_prep_2026-05-04_for_ken.pdf from the markdown source.

One-shot script — drop into data/qa_data/ alongside the .md, run with arcgispro-py3.
TRPA-branded (navy header, blue accents, Helvetica = closest built-in to Open Sans).
"""
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


HERE = Path(__file__).resolve().parent
OUT = HERE / "meeting_prep_2026-05-04_for_ken.pdf"

# TRPA brand
TRPA_BLUE   = HexColor("#0072CE")
TRPA_NAVY   = HexColor("#003B71")
TRPA_FOREST = HexColor("#4A6118")
TRPA_ORANGE = HexColor("#E87722")
TRPA_ICE    = HexColor("#B4CBE8")
TRPA_GRAY   = HexColor("#5d6c7e")
TRPA_BORDER = HexColor("#e1e7ee")


def make_styles():
    base = getSampleStyleSheet()
    s = {}
    s["title"] = ParagraphStyle(
        "Title", parent=base["Title"],
        fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=TRPA_NAVY,
        spaceAfter=6,
    )
    s["meta"] = ParagraphStyle(
        "Meta", parent=base["Normal"],
        fontName="Helvetica", fontSize=9, leading=13, textColor=TRPA_GRAY,
        spaceAfter=2,
    )
    s["h2"] = ParagraphStyle(
        "H2", parent=base["Heading2"],
        fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=TRPA_NAVY,
        spaceBefore=18, spaceAfter=6,
    )
    s["body"] = ParagraphStyle(
        "Body", parent=base["BodyText"],
        fontName="Helvetica", fontSize=10, leading=14.5, textColor=HexColor("#1a2332"),
        spaceAfter=8,
    )
    s["bullet"] = ParagraphStyle(
        "Bullet", parent=s["body"], leftIndent=14, bulletIndent=2,
        fontSize=10, leading=14.5, spaceAfter=4,
    )
    s["link"] = ParagraphStyle(
        "Link", parent=s["body"], textColor=TRPA_BLUE,
    )
    s["small"] = ParagraphStyle(
        "Small", parent=s["body"], fontSize=8.5, leading=12, textColor=TRPA_GRAY,
    )
    return s


def header_band(doc):
    """Draw the navy header band on page 1 only — handled at canvas level."""
    pass


def on_first_page(canvas, doc):
    canvas.saveState()
    # Navy band across the top
    canvas.setFillColor(TRPA_NAVY)
    canvas.rect(0, letter[1] - 0.5 * inch, letter[0], 0.5 * inch, stroke=0, fill=1)
    # Brand accent stripe (forest -> blue -> orange)
    stripe_h = 0.06 * inch
    seg = letter[0] / 3
    canvas.setFillColor(TRPA_FOREST); canvas.rect(0,         letter[1] - 0.5 * inch - stripe_h, seg, stripe_h, stroke=0, fill=1)
    canvas.setFillColor(TRPA_BLUE);   canvas.rect(seg,       letter[1] - 0.5 * inch - stripe_h, seg, stripe_h, stroke=0, fill=1)
    canvas.setFillColor(TRPA_ORANGE); canvas.rect(2 * seg,   letter[1] - 0.5 * inch - stripe_h, seg, stripe_h, stroke=0, fill=1)
    # Eyebrow text
    canvas.setFillColor(TRPA_ICE)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(0.6 * inch, letter[1] - 0.32 * inch, "TAHOE REGIONAL PLANNING AGENCY")
    # Page footer
    canvas.setFillColor(TRPA_GRAY)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(0.6 * inch, 0.4 * inch, "Meeting prep — QA tracking + parcel data handoff")
    canvas.drawRightString(letter[0] - 0.6 * inch, 0.4 * inch, f"Page {doc.page}")
    canvas.restoreState()


def on_later_page(canvas, doc):
    canvas.saveState()
    # Lighter top stripe on continuation pages
    canvas.setFillColor(TRPA_BLUE)
    canvas.rect(0, letter[1] - 0.06 * inch, letter[0], 0.06 * inch, stroke=0, fill=1)
    canvas.setFillColor(TRPA_GRAY)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(0.6 * inch, 0.4 * inch, "Meeting prep — QA tracking + parcel data handoff")
    canvas.drawRightString(letter[0] - 0.6 * inch, 0.4 * inch, f"Page {doc.page}")
    canvas.restoreState()


def link(text, url):
    return f'<a href="{url}" color="#0072CE">{text}</a>'


def code(text):
    return f'<font face="Courier" color="#003B71">{text}</font>'


def build_doc():
    doc = SimpleDocTemplate(
        str(OUT), pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.85 * inch, bottomMargin=0.7 * inch,
        title="Meeting prep — QA tracking schema + parcel data handoff",
        author="Mason Bindl",
    )
    s = make_styles()
    story = []

    story.append(Paragraph("Meeting prep — QA tracking schema + parcel data handoff", s["title"]))
    story.append(Paragraph("<b>For:</b> Kenneth Kasman &nbsp;&middot;&nbsp; <b>From:</b> Mason Bindl &nbsp;&middot;&nbsp; <b>Date:</b> May 4, 2026", s["meta"]))
    story.append(Paragraph("<b>Re:</b> Your three asks (schema walkthrough + parcel genealogy + 2012&ndash;2026 parcel data)", s["meta"]))
    story.append(Spacer(1, 14))

    story.append(Paragraph(
        "Quick prep for our chat. Three asks from your message &mdash; here&rsquo;s what&rsquo;s ready and what needs a confirm-from-you.",
        s["body"],
    ))

    # ── 1 ──
    story.append(Paragraph("1. QA tracking schema (the main ask) &mdash; <font color='#4A6118'>ready</font>", s["h2"]))
    story.append(Paragraph(
        "We&rsquo;ve prototyped the database for tracking changes to your previously-reported Cumulative Accounting data. "
        "It&rsquo;s a sidecar table called " + code("QaCorrectionDetail") + " that hangs off a broader "
        + code("ParcelDevelopmentChangeEvent") + " table, with a 1-to-(0 or 1) relationship triggered when "
        + code("ChangeSource = 'qa_correction'") + ". Key design choices:",
        s["body"],
    ))
    bullets_1 = [
        "<b>Annual reporting cadence + periodic big-sweep campaigns</b> (your 2023 + 2026) &mdash; the schema models both. "
        + code("ReportingYear") + " is any annual value; " + code("SweepCampaign") + " is a nullable tag for sweep years specifically.",
        "<b>9-value controlled vocabulary</b> for " + code("CorrectionCategory") + ", sourced directly from your Sheet2.",
        "<b>" + code("RawAPN") + " audit column</b> preserves the pre-canonicalization APN string for traceability.",
        "<b>APN canonicalization</b> as a single function ("
        + code("parcel_development_history_etl/utils.py:canonical_apn") + ") used by all three tracks.",
    ]
    for b in bullets_1:
        story.append(Paragraph("&bull; " + b, s["bullet"]))

    story.append(Spacer(1, 8))
    story.append(Paragraph("Three things to look at before / during the meeting:", s["body"]))
    refs_1 = [
        "<b>Concise track doc:</b> " + link("erd/qa_corrections_track.md", "https://github.com/trpa-agency/Reporting/blob/MTB-Edits/erd/qa_corrections_track.md")
        + " &mdash; overview, data flow diagram, refresh workflow, open issues",
        "<b>The actual schema:</b> " + link("erd/target_schema.md", "https://github.com/trpa-agency/Reporting/blob/MTB-Edits/erd/target_schema.md")
        + ", section &ldquo;ERD &mdash; QA corrections sidecar (Track C)&rdquo;",
        "<b>Working dashboard:</b> " + link("html/qa-change-rationale.html", "https://github.com/trpa-agency/Reporting/blob/MTB-Edits/html/qa-change-rationale.html")
        + " &mdash; open in any browser; AG Grid filterable by year/sweep/canonicality, sidebar bar chart of top correction categories color-coded canonical (navy) vs noncanonical (orange)",
    ]
    for r in refs_1:
        story.append(Paragraph("&bull; " + r, s["bullet"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "The dashboard already loaded your " + code("CA Changes breakdown.xlsx")
        + " end-to-end: <b>5,925 normalized change events</b>, <b>218,192 reconciliation findings</b> labeled against the existing "
        + code("s06_qa.py") + " automated detection outputs.",
        s["body"],
    ))

    # ── 2 ──
    story.append(Paragraph("2. Final parcel genealogy lookups &mdash; <font color='#4A6118'>ready</font>", s["h2"]))
    story.append(Paragraph(
        "The consolidated lookup is at " + code("data/qa_data/apn_genealogy_master.csv")
        + " (297 KB, 5-source merge). Plus the 4 unmerged source files if you want to see lineage:",
        s["body"],
    ))
    geneal_data = [
        ["File", "Source"],
        ["apn_genealogy_master.csv", "the consolidated merge — what you probably want"],
        ["apn_genealogy_tahoe.csv", "your historical genealogy data"],
        ["apn_genealogy_accela.csv", "from Accela permit records"],
        ["apn_genealogy_ltinfo.csv", "from LT Info"],
        ["apn_genealogy_spatial.csv", "derived from spatial overlap analysis"],
    ]
    t = Table(geneal_data, colWidths=[2.2 * inch, 4.4 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TRPA_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#ffffff")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("FONTNAME", (0, 1), (0, -1), "Courier"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#ffffff"), HexColor("#f5f7fa")]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, TRPA_BLUE),
        ("BOX", (0, 0), (-1, -1), 0.5, TRPA_BORDER),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "I can attach all 5 to an email, share via OneDrive, or you can clone the repo (MTB-Edits branch) &mdash; let me know which path is easiest on your end.",
        s["body"],
    ))

    # ── 3 ──
    story.append(Paragraph("3. Final 2012&ndash;2026 parcel-level data &mdash; <font color='#E87722'>needs format confirm</font>", s["h2"]))
    story.append(Paragraph(
        "The " + code("parcel_development_history_etl") + " pipeline produces a feature class called "
        + code("OUTPUT_FC") + " that&rsquo;s the canonical 2012&ndash;2026 per-APN per-year residential development data. "
        "Roughly 50K rows &times; 15 columns, including geometry. Need to know what format works best for your end:",
        s["body"],
    ))
    for b in [
        "<b>CSV export</b> &mdash; flat table, easiest for Excel / pandas work",
        "<b>Shapefile</b> &mdash; preserves geometry for ArcMap / Pro",
        "<b>Direct GDB read access</b> &mdash; if you want to query live",
    ]:
        story.append(Paragraph("&bull; " + b, s["bullet"]))
    story.append(Paragraph("Tell me the format and I&rsquo;ll send within the day.", s["body"]))

    # ── 4 — Optional homework ──
    story.append(Paragraph("4. One thing for you to look at (optional homework)", s["h2"]))
    story.append(Paragraph(
        "When the loader normalized your CA Changes XLSX, only <b>30.2% of your Sheet1 category labels matched the controlled vocabulary in your Sheet2</b>. "
        "The other 70% paraphrase rather than match exactly. We pulled together a triage CSV with the <b>17 unique noncanonical labels</b>, "
        "their occurrence counts, and 5 sample APNs each:",
        s["body"],
    ))
    for r in [
        "<b>Explainer:</b> " + link("data/qa_data/correction_category_mapping_TODO.md", "https://github.com/trpa-agency/Reporting/blob/MTB-Edits/data/qa_data/correction_category_mapping_TODO.md"),
        "<b>Triage CSV:</b> " + link("data/qa_data/correction_category_mapping.csv", "https://github.com/trpa-agency/Reporting/blob/MTB-Edits/data/qa_data/correction_category_mapping.csv"),
    ]:
        story.append(Paragraph("&bull; " + r, s["bullet"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("The top 5 noncanonical labels alone account for ~80% of the mismatches:", s["body"]))

    top5 = [
        ["Reporting year", "Label", "Occurrences"],
        ["2023", "Corrections - Units Removed Based on County Data", "890"],
        ["2023", "Unit(s) not previously counted. Constructed in or before 2012. Verified with County.", "733"],
        ["2023", "Correction Based on County Data", "696"],
        ["2023", "Mobile Home Park Corrections", "582"],
        ["2023", "Over-Correction", "349"],
    ]
    t = Table(top5, colWidths=[0.95 * inch, 4.65 * inch, 1.0 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TRPA_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#ffffff")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("FONTNAME", (-1, 1), (-1, -1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#ffffff"), HexColor("#f5f7fa")]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, TRPA_BLUE),
        ("BOX", (0, 0), (-1, -1), 0.5, TRPA_BORDER),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "If you can fill in the " + code("canonical_label") + " column (map to existing Sheet2 vocab, or invent a new label and we&rsquo;ll add it), "
        "the dashboard&rsquo;s match rate jumps from 30% to ~100%.",
        s["body"],
    ))

    # ── Agenda ──
    story.append(Paragraph("Suggested 30-minute agenda", s["h2"]))
    agenda = [
        ["Min", "What"],
        ["0–3",   "Context recap — three-track framing (Genealogy / Allocations / QA Corrections); where your CA Changes data fits"],
        ["3–10",  "Walk through the QaCorrectionDetail schema; why we chose sidecar over column extension"],
        ["10–15", "Loader demo — your XLSX → normalized rows (~30 sec live run)"],
        ["15–22", "Dashboard E1 demo + the 30% canonical-vocab triage discussion"],
        ["22–27", "Hand-off — genealogy CSVs + parcel-level data format confirmation"],
        ["27–30", "Open questions, cadence going forward, next steps"],
    ]
    t = Table(agenda, colWidths=[0.6 * inch, 6.0 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TRPA_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#ffffff")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 1), (0, -1), TRPA_BLUE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#ffffff"), HexColor("#f5f7fa")]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, TRPA_BLUE),
        ("BOX", (0, 0), (-1, -1), 0.5, TRPA_BORDER),
    ]))
    story.append(t)

    # ── Three questions ──
    story.append(Paragraph("Three quick questions to think about", s["h2"]))
    for i, q in enumerate([
        "<b>Mapping approach</b> &mdash; expand Sheet2 to include the 17 noncanonical labels you&rsquo;ve been using, OR keep Sheet2 tight and maintain a separate "
        + code("correction_category_mapping.csv") + " lookup?",
        "<b>Parcel-level data format</b> &mdash; CSV / shapefile / direct GDB access for the 2012&ndash;2026 OUTPUT_FC?",
        "<b>CA Changes XLSX cadence</b> &mdash; are you maintaining it continuously (rolling corrections every reporting year), or only during sweep campaigns? Affects how often we re-run the loader.",
    ], 1):
        story.append(Paragraph(f"<b>{i}.</b> " + q, s["bullet"]))

    # ── Quick links ──
    story.append(Paragraph("Quick links (all on the MTB-Edits branch)", s["h2"]))
    links = [
        ("Track doc",        "erd/qa_corrections_track.md", "https://github.com/trpa-agency/Reporting/blob/MTB-Edits/erd/qa_corrections_track.md"),
        ("Schema",           "erd/target_schema.md",        "https://github.com/trpa-agency/Reporting/blob/MTB-Edits/erd/target_schema.md"),
        ("Dashboard",        "html/qa-change-rationale.html", "https://github.com/trpa-agency/Reporting/blob/MTB-Edits/html/qa-change-rationale.html"),
        ("Your action item", "data/qa_data/correction_category_mapping.csv", "https://github.com/trpa-agency/Reporting/blob/MTB-Edits/data/qa_data/correction_category_mapping.csv"),
        ("Genealogy master", "data/qa_data/apn_genealogy_master.csv", "https://github.com/trpa-agency/Reporting/blob/MTB-Edits/data/qa_data/apn_genealogy_master.csv"),
        ("Repo root",        "MTB-Edits branch",            "https://github.com/trpa-agency/Reporting/tree/MTB-Edits"),
    ]
    for label_, path, url in links:
        story.append(Paragraph(
            f"&bull; <b>{label_}:</b> " + link(path, url), s["bullet"],
        ))

    story.append(Spacer(1, 18))
    story.append(Paragraph("Talk soon &mdash; <br/>Mason", s["body"]))

    doc.build(story, onFirstPage=on_first_page, onLaterPages=on_later_page)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build_doc()
