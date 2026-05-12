// Build dashboard_content_review.docx — Word doc with content + screenshots
// of every active TRPA dashboard, formatted for Ken to mark up via track changes.

const fs   = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
  Header, Footer, AlignmentType, PageOrientation, LevelFormat,
  ExternalHyperlink, TabStopType, TabStopPosition,
  HeadingLevel, BorderStyle, WidthType, ShadingType,
  PageNumber, PageBreak,
} = require("docx");

const REPO   = path.resolve(__dirname, "..");
const SHOTS  = path.join(__dirname, "dashboard_screenshots");
const DATA   = JSON.parse(fs.readFileSync(path.join(__dirname, "dashboard_content.json"), "utf-8"));
const OUT    = path.join(REPO, "outputs", "dashboard_content_review.docx");

// US Letter portrait, 1-inch margins → content area 6.5"x9" = 624x864 px @ 96dpi.
const CONTENT_W = 624;
const CONTENT_H = 864;
const MAX_IMG_H = 720; // leave room for caption + bottom margin

// TRPA brand colors (used for table shading + heading runs)
const NAVY    = "003B71";
const BLUE    = "0072CE";
const ORANGE  = "E87722";
const FOREST  = "4A6118";
const ICE     = "B4CBE8";
const BG      = "F5F7FA";
const BORDER  = "D8DDE6";

// ───────────────────────────────────────────────────────────────────
// helpers
// ───────────────────────────────────────────────────────────────────

function p(text, opts = {}) {
  return new Paragraph({
    spacing: opts.spacing || { after: 80 },
    alignment: opts.alignment,
    heading: opts.heading,
    children: [new TextRun({ text: text, bold: opts.bold, italics: opts.italics,
                             color: opts.color, size: opts.size, font: opts.font })],
  });
}

function blank() {
  return new Paragraph({ children: [new TextRun("")], spacing: { after: 60 } });
}

function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}

function hyperlink(label, url) {
  return new ExternalHyperlink({
    children: [new TextRun({ text: label, style: "Hyperlink", color: BLUE })],
    link: url,
  });
}

function imageFor(slug) {
  const filename = `${slug}.png`;
  const filepath = path.join(SHOTS, filename);
  const buf = fs.readFileSync(filepath);
  // figure intrinsic size — naive PNG header parse (8-byte sig + 16 bytes to width/height)
  const w = buf.readUInt32BE(16);
  const h = buf.readUInt32BE(20);
  const scale = Math.min(CONTENT_W / w, MAX_IMG_H / h);
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 120, after: 120 },
    children: [new ImageRun({
      type: "png",
      data: buf,
      transformation: { width: Math.round(w * scale), height: Math.round(h * scale) },
      altText: { title: filename, description: `Screenshot of ${slug}`, name: filename },
    })],
  });
}

// Two-column "label : value" table for KPI / section copy
function copyTable(rows, leftHeader = "Label", rightHeader = "Description") {
  const border = { style: BorderStyle.SINGLE, size: 4, color: BORDER };
  const borders = { top: border, bottom: border, left: border, right: border };
  const COL_L = 2880, COL_R = 6480; // 2 + 4.5 inches

  const headerRow = new TableRow({
    tableHeader: true,
    children: [
      new TableCell({
        borders, width: { size: COL_L, type: WidthType.DXA },
        shading: { fill: NAVY, type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({ children: [new TextRun({ text: leftHeader, bold: true, color: "FFFFFF", size: 20 })] })],
      }),
      new TableCell({
        borders, width: { size: COL_R, type: WidthType.DXA },
        shading: { fill: NAVY, type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({ children: [new TextRun({ text: rightHeader, bold: true, color: "FFFFFF", size: 20 })] })],
      }),
    ],
  });

  const dataRows = rows.map((r, i) => new TableRow({
    children: [
      new TableCell({
        borders, width: { size: COL_L, type: WidthType.DXA },
        shading: { fill: i % 2 === 0 ? "FFFFFF" : BG, type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({ children: [new TextRun({ text: r[0] || "", bold: true, size: 20 })] })],
      }),
      new TableCell({
        borders, width: { size: COL_R, type: WidthType.DXA },
        shading: { fill: i % 2 === 0 ? "FFFFFF" : BG, type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({ children: [new TextRun({ text: r[1] || "", size: 20 })] })],
      }),
    ],
  }));

  return new Table({
    width: { size: COL_L + COL_R, type: WidthType.DXA },
    columnWidths: [COL_L, COL_R],
    rows: [headerRow, ...dataRows],
  });
}

// ───────────────────────────────────────────────────────────────────
// cover page
// ───────────────────────────────────────────────────────────────────

const cover = [
  p("TRPA", { color: BLUE, bold: true, size: 28, spacing: { after: 40 } }),
  p("Cumulative Accounting Dashboards", { bold: true, size: 56, color: NAVY, spacing: { after: 40 } }),
  p("Content review — track changes copy", { bold: true, size: 32, color: NAVY, spacing: { after: 480 } }),
  p("Prepared for Ken Kasman + Dan Segan", { italics: true, size: 24, color: "5D6C7E", spacing: { after: 240 } }),
  p(new Date().toISOString().slice(0, 10), { size: 24, color: "5D6C7E", spacing: { after: 720 } }),

  // How-to callout
  new Paragraph({
    border: { top: { style: BorderStyle.SINGLE, size: 12, color: BLUE, space: 8 } },
    spacing: { before: 240, after: 80 },
    children: [new TextRun({ text: "How to use this document", bold: true, size: 26, color: NAVY })],
  }),
  new Paragraph({
    spacing: { after: 80 },
    children: [new TextRun({ text: "This document captures the visible copy of all 8 active TRPA cumulative-accounting dashboards plus a screenshot of each. ", size: 22 })],
  }),
  new Paragraph({
    spacing: { after: 80 },
    children: [
      new TextRun({ text: "Mark edits using Word ", size: 22 }),
      new TextRun({ text: "Track Changes", size: 22, italics: true, bold: true }),
      new TextRun({ text: " (Review → Track Changes → All Markup). Add comments via Review → New Comment. Send the marked-up file back to Mason for integration.", size: 22 }),
    ],
  }),
  new Paragraph({
    spacing: { after: 80 },
    children: [new TextRun({ text: "Numerical values shown in the screenshots are live-as-of the screenshot timestamp; copy review focuses on labels, descriptions, and narrative text rather than the data values themselves.", size: 22 })],
  }),

  new Paragraph({
    spacing: { before: 480, after: 80 },
    children: [new TextRun({ text: "Active dashboards in this review", bold: true, size: 24, color: NAVY })],
  }),
];

DATA.forEach((d, i) => {
  cover.push(new Paragraph({
    spacing: { after: 40 },
    children: [
      new TextRun({ text: `${i + 1}.  `, size: 22, color: BLUE }),
      new TextRun({ text: d.friendly_title, size: 22, bold: true }),
      new TextRun({ text: `  ·  ${d.track}  ·  ${d.audience}`, size: 20, color: "5D6C7E" }),
    ],
  }));
});

cover.push(pageBreak());

// ───────────────────────────────────────────────────────────────────
// per-dashboard sections
// ───────────────────────────────────────────────────────────────────

const dashboardSections = [];

DATA.forEach((d, idx) => {
  // section heading
  dashboardSections.push(new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 240, after: 80 },
    children: [
      new TextRun({ text: `${idx + 1}. ${d.friendly_title}`, bold: true, size: 36, color: NAVY }),
    ],
  }));

  // meta line
  dashboardSections.push(new Paragraph({
    spacing: { after: 60 },
    children: [
      new TextRun({ text: "Track: ", size: 20, bold: true, color: "5D6C7E" }),
      new TextRun({ text: d.track + "   ", size: 20 }),
      new TextRun({ text: "Audience: ", size: 20, bold: true, color: "5D6C7E" }),
      new TextRun({ text: d.audience + "   ", size: 20 }),
      new TextRun({ text: "File: ", size: 20, bold: true, color: "5D6C7E" }),
      new TextRun({ text: d.html_file, size: 20, font: "Consolas" }),
    ],
  }));
  dashboardSections.push(new Paragraph({
    spacing: { after: 160 },
    children: [
      new TextRun({ text: "Live URL: ", size: 20, bold: true, color: "5D6C7E" }),
      hyperlink(d.github_pages_url, d.github_pages_url),
    ],
  }));

  // screenshot
  dashboardSections.push(imageFor(d.slug));

  // header copy
  dashboardSections.push(new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 120, after: 80 },
    children: [new TextRun({ text: "Header copy", size: 26, bold: true, color: NAVY })],
  }));
  const headerRows = [];
  if (d.eyebrow)  headerRows.push(["Eyebrow",  d.eyebrow]);
  if (d.title)    headerRows.push(["Title",    d.title]);
  if (d.subtitle) headerRows.push(["Subtitle / tagline", d.subtitle]);
  if (d.meta)     headerRows.push(["Header meta (top right)", d.meta]);
  dashboardSections.push(copyTable(headerRows, "Element", "Text"));
  dashboardSections.push(blank());

  // KPI cards
  if (d.kpis.length) {
    dashboardSections.push(new Paragraph({
      heading: HeadingLevel.HEADING_2,
      spacing: { before: 120, after: 80 },
      children: [new TextRun({ text: "KPI cards", size: 26, bold: true, color: NAVY })],
    }));
    dashboardSections.push(copyTable(
      d.kpis.map(k => [k.label, k.sub]),
      "Label", "Sub-text",
    ));
    dashboardSections.push(blank());
  }

  // Section / chart copy
  if (d.sections.length) {
    dashboardSections.push(new Paragraph({
      heading: HeadingLevel.HEADING_2,
      spacing: { before: 120, after: 80 },
      children: [new TextRun({ text: "Section headings", size: 26, bold: true, color: NAVY })],
    }));
    dashboardSections.push(copyTable(
      d.sections.map(s => [s.title, s.description || "(no description)"]),
      "Heading", "Description",
    ));
    dashboardSections.push(blank());
  }

  // Controls
  if (d.controls && d.controls.length) {
    dashboardSections.push(new Paragraph({
      heading: HeadingLevel.HEADING_2,
      spacing: { before: 120, after: 60 },
      children: [new TextRun({ text: "Control labels (buttons / toggles)", size: 26, bold: true, color: NAVY })],
    }));
    dashboardSections.push(new Paragraph({
      spacing: { after: 80 },
      children: [new TextRun({ text: d.controls.join(" · "), size: 22, italics: true })],
    }));
  }

  // Footnote / attribution
  if (d.footnote) {
    dashboardSections.push(new Paragraph({
      heading: HeadingLevel.HEADING_2,
      spacing: { before: 120, after: 80 },
      children: [new TextRun({ text: "Footnote / data attribution", size: 26, bold: true, color: NAVY })],
    }));
    dashboardSections.push(new Paragraph({
      spacing: { after: 80 },
      shading: { fill: BG, type: ShadingType.CLEAR },
      children: [new TextRun({ text: d.footnote, size: 20, color: "5D6C7E" })],
    }));
  }

  // page break between dashboards
  if (idx < DATA.length - 1) dashboardSections.push(pageBreak());
});

// ───────────────────────────────────────────────────────────────────
// closing notes
// ───────────────────────────────────────────────────────────────────

const closing = [
  pageBreak(),
  new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 240, after: 80 },
    children: [new TextRun({ text: "Notes & open questions for the team", size: 36, bold: true, color: NAVY })],
  }),
  p("Use this section to capture any cross-cutting questions, vocabulary suggestions, or items that touch more than one dashboard.", { size: 22, spacing: { after: 240 } }),

  p("Cross-dashboard reconciliation (verified after Ken's April 2026 update):", { size: 24, bold: true, color: NAVY, spacing: { after: 80 } }),
  new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children: [new TextRun({ text: "Allocation Tracking KPIs sum to 2,600 (Private dev pool 832 + Jurisdiction pool 844 + TRPA pool 924).", size: 22 })],
  }),
  new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children: [new TextRun({ text: "Regional Plan Capacity Dial 2012 Plan additional cards sum to 2,600 (Constructed 681 + Private dev pool not built 151 + Jurisdiction pool 844 + TRPA pool 924).", size: 22 })],
  }),
  new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children: [new TextRun({ text: "Pool Balance Cards staff total 991 = 154 TRPA + 837 jurisdictions (matches Ken's xlsx exactly).", size: 22 })],
  }),
  new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children: [new TextRun({ text: "Public Allocation Availability totals 841 = 837 jurisdictions + 4 Carson (Ken's table excludes Carson; we keep it for completeness).", size: 22 })],
  }),

  p("", { spacing: { after: 240 } }),
  p("Ken's review focus suggestions:", { size: 24, bold: true, color: NAVY, spacing: { after: 80 } }),
  new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children: [new TextRun({ text: "Pool / state vocabulary — does 'TRPA pool', 'Jurisdiction pool', 'Private development pool' read correctly to a developer or board member?", size: 22 })],
  }),
  new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children: [new TextRun({ text: "Source-of-rights labels — 'Allocation / Banked / Transfer / Conversion / Bonus Unit' — any of these confusing or duplicative?", size: 22 })],
  }),
  new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children: [new TextRun({ text: "Era cutoff labels — 'Pre-1987 Plan', '1987 Plan', '2012 Plan' — preferred phrasing for non-staff audience?", size: 22 })],
  }),
  new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children: [new TextRun({ text: "Footnote attribution language — do data sources need to be more / less prominent on the public-facing pages?", size: 22 })],
  }),
];

// ───────────────────────────────────────────────────────────────────
// document
// ───────────────────────────────────────────────────────────────────

const doc = new Document({
  creator: "TRPA Reporting",
  title: "TRPA Cumulative Accounting Dashboards — Content Review",
  description: "Word doc snapshot of all active TRPA cumulative-accounting dashboards for content review via track changes.",
  styles: {
    default: {
      document: { run: { font: "Open Sans", size: 22 } },
      hyperlink: { run: { color: "0072CE", underline: { type: "single" } } },
    },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run:       { size: 36, bold: true, font: "Open Sans", color: NAVY },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run:       { size: 26, bold: true, font: "Open Sans", color: NAVY },
        paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 1 } },
    ],
  },
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: "•",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } },
      }],
    }],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          children: [new TextRun({
            text: "TRPA dashboards — content review draft",
            size: 16, color: "8A9BB2", italics: true,
          })],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "Page ", size: 16, color: "8A9BB2" }),
            new TextRun({ children: [PageNumber.CURRENT], size: 16, color: "8A9BB2" }),
            new TextRun({ text: " of ", size: 16, color: "8A9BB2" }),
            new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: "8A9BB2" }),
          ],
        })],
      }),
    },
    children: [...cover, ...dashboardSections, ...closing],
  }],
});

fs.mkdirSync(path.dirname(OUT), { recursive: true });
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log(`Wrote ${OUT} (${(buf.length / 1024).toFixed(0)} KB)`);
});
