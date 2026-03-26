"""
reports/generator.py

Generates branded PDF reports from AI-produced content + scoring data.
Uses reportlab Platypus for multi-page layout.
Professional enterprise scorecard layout (Qualys-style light theme).
"""

import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, Flowable
)
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics import renderPDF

# ── Brand / palette ───────────────────────────────────────────────────────────
BRAND_DARK   = HexColor("#1a1f2e")   # dark navy  (header/footer bands)
BRAND_ACCENT = HexColor("#e63946")   # red accent
BRAND_MID    = HexColor("#2d3561")   # mid blue
BRAND_LIGHT  = HexColor("#f1f3f5")   # light gray bg
PAGE_BG      = white                 # white page body
SECTION_HDR  = HexColor("#eef0f5")   # very light gray for section header rows
TEXT_MAIN    = HexColor("#1a1f2e")
TEXT_MUTED   = HexColor("#6c757d")
GRID_LINE    = HexColor("#dee2e6")

CRITICAL_COLOR = HexColor("#dc3545")
HIGH_COLOR     = HexColor("#fd7e14")
MEDIUM_COLOR   = HexColor("#e0a800")   # slightly darker yellow for readability
LOW_COLOR      = HexColor("#28a745")

PRIORITY_COLORS = {
    "CRITICAL": CRITICAL_COLOR,
    "HIGH":     HIGH_COLOR,
    "MEDIUM":   MEDIUM_COLOR,
    "LOW":      LOW_COLOR,
}

# CIS IG1 controls in display order — must align with scoring engine IDs
_CIS_DISPLAY = [
    ("C1",    "Asset Inventory"),
    ("C2",    "Software Inventory"),
    ("C3",    "Data Protection (DLP)"),
    ("C4",    "Secure Config of Assets"),
    ("C5",    "Privileged Account Separation"),
    ("C5",    "Password Policy Enforcement"),
    ("C5-C6", "Centralized Account/Access Mgmt"),
    ("C6",    "Multi-Factor Authentication"),
    ("C7",    "Vulnerability Management"),
    ("C7",    "Patch Management Cadence"),
    ("C8",    "Logging / SIEM"),
    ("C9",    "Email Security / Anti-Phishing"),
    ("C10",   "Malware Defenses (EDR)"),
    ("C10",   "USB / Removable Media Control"),
    ("C11",   "Data Recovery / Backup"),
    ("C11",   "Backup Testing"),
    ("C13",   "Firewall / Perimeter Defense"),
    ("C13",   "Network Monitoring / Defense"),
    ("C14",   "Security Awareness Training"),
    ("C15",   "Vendor / Third-Party Access Mgmt"),
    ("C16",   "Application Allow-Listing"),
    ("C17",   "Incident Response Plan"),
]


# ── Custom Flowable: accent-bar section title ─────────────────────────────────

class AccentHeader(Flowable):
    """Draws a colored left-side accent bar beside a section title."""

    def __init__(self, text, bar_color=BRAND_MID, font_size=13, width=7*inch):
        super().__init__()
        self.text = text
        self.bar_color = bar_color
        self.font_size = font_size
        self._width = width
        self.height = font_size + 14

    def draw(self):
        bar_w = 4
        bar_h = self.font_size + 6
        self.canv.setFillColor(self.bar_color)
        self.canv.rect(0, 2, bar_w, bar_h, fill=1, stroke=0)
        self.canv.setFillColor(TEXT_MAIN)
        self.canv.setFont("Helvetica-Bold", self.font_size)
        self.canv.drawString(bar_w + 8, 6, self.text)

    def wrap(self, availWidth, availHeight):
        return (self._width, self.height)


# ── Styles ────────────────────────────────────────────────────────────────────

def _build_styles():
    styles = {
        "title": ParagraphStyle(
            "ReportTitle",
            fontSize=22, fontName="Helvetica-Bold",
            textColor=white, spaceAfter=4, alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            fontSize=12, fontName="Helvetica",
            textColor=HexColor("#adb5bd"), spaceAfter=4, alignment=TA_LEFT,
        ),
        "h1": ParagraphStyle(
            "H1", fontSize=13, fontName="Helvetica-Bold",
            textColor=TEXT_MAIN, spaceBefore=16, spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "H2", fontSize=11, fontName="Helvetica-Bold",
            textColor=BRAND_MID, spaceBefore=12, spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "Body", fontSize=10, fontName="Helvetica",
            textColor=TEXT_MAIN, spaceAfter=6, leading=15,
        ),
        "muted": ParagraphStyle(
            "Muted", fontSize=9, fontName="Helvetica",
            textColor=TEXT_MUTED, spaceAfter=3,
        ),
        "table_header": ParagraphStyle(
            "TableHeader", fontSize=8, fontName="Helvetica-Bold",
            textColor=white, alignment=TA_CENTER,
        ),
        "table_cell": ParagraphStyle(
            "TableCell", fontSize=8, fontName="Helvetica",
            textColor=TEXT_MAIN, leading=12,
        ),
        "score_big": ParagraphStyle(
            "ScoreBig", fontSize=52, fontName="Helvetica-Bold",
            textColor=BRAND_ACCENT, alignment=TA_CENTER,
        ),
        "score_label": ParagraphStyle(
            "ScoreLabel", fontSize=10, fontName="Helvetica",
            textColor=TEXT_MUTED, alignment=TA_CENTER,
        ),
        "pass_tag": ParagraphStyle(
            "PassTag", fontSize=8, fontName="Helvetica-Bold",
            textColor=LOW_COLOR, alignment=TA_CENTER,
        ),
        "fail_tag": ParagraphStyle(
            "FailTag", fontSize=8, fontName="Helvetica-Bold",
            textColor=CRITICAL_COLOR, alignment=TA_CENTER,
        ),
        "warn_tag": ParagraphStyle(
            "WarnTag", fontSize=8, fontName="Helvetica-Bold",
            textColor=HIGH_COLOR, alignment=TA_CENTER,
        ),
    }
    return styles


# ── Page header / footer (unchanged signature) ────────────────────────────────

def _header_footer(canvas, doc):
    """Page header and footer on every page."""
    canvas.saveState()
    w, h = letter

    # Header bar
    canvas.setFillColor(BRAND_DARK)
    canvas.rect(0, h - 0.5 * inch, w, 0.5 * inch, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(0.5 * inch, h - 0.32 * inch, "CONFIDENTIAL — MSSP SECURITY ASSESSMENT")
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(w - 0.5 * inch, h - 0.32 * inch, datetime.now().strftime("%B %d, %Y"))

    # Footer
    canvas.setFillColor(BRAND_LIGHT)
    canvas.rect(0, 0, w, 0.4 * inch, fill=1, stroke=0)
    canvas.setFillColor(TEXT_MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(0.5 * inch, 0.14 * inch,
        "This report is confidential and intended solely for the named recipient.")
    canvas.drawRightString(w - 0.5 * inch, 0.14 * inch, f"Page {doc.page}")

    canvas.restoreState()


# ── Gauge bar (canvas drawing embedded via Flowable) ─────────────────────────

class GaugeBar(Flowable):
    """Horizontal 0-100 gauge bar with a score marker."""

    def __init__(self, score, width=3.2*inch, height=0.38*inch):
        super().__init__()
        self._w = width
        self._h = height
        self.score = score

    def wrap(self, availWidth, availHeight):
        return (self._w, self._h + 18)

    def draw(self):
        c = self.canv
        w, h = self._w, self._h
        score = self.score

        # Background track
        c.setFillColor(GRID_LINE)
        c.roundRect(0, 10, w, h, 3, fill=1, stroke=0)

        # Filled portion — color based on score
        fill_w = (score / 100) * w
        if score >= 75:
            fill_color = CRITICAL_COLOR
        elif score >= 55:
            fill_color = HIGH_COLOR
        elif score >= 35:
            fill_color = MEDIUM_COLOR
        else:
            fill_color = LOW_COLOR
        c.setFillColor(fill_color)
        c.roundRect(0, 10, fill_w, h, 3, fill=1, stroke=0)

        # Tick labels
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 7)
        for val in (0, 25, 50, 75, 100):
            x = (val / 100) * w
            c.drawCentredString(x, 1, str(val))

        # Score marker triangle
        mx = (score / 100) * w
        c.setFillColor(TEXT_MAIN)
        p = c.beginPath()
        p.moveTo(mx - 4, 10)
        p.lineTo(mx + 4, 10)
        p.lineTo(mx, 5)
        p.close()
        c.drawPath(p, fill=1, stroke=0)


# ── Pie chart for gap distribution ───────────────────────────────────────────

def _build_gap_pie(gaps, size=140):
    """Return a Drawing containing a donut-style pie chart of gap priorities."""
    crit  = sum(1 for g in gaps if g["priority"] == "CRITICAL")
    high  = sum(1 for g in gaps if g["priority"] == "HIGH")
    med   = sum(1 for g in gaps if g["priority"] == "MEDIUM")
    low   = sum(1 for g in gaps if g["priority"] == "LOW")

    # Build data / labels only for non-zero slices
    data   = []
    labels = []
    clrs   = []
    for count, label, clr in [
        (crit, "Critical", CRITICAL_COLOR),
        (high, "High",     HIGH_COLOR),
        (med,  "Medium",   MEDIUM_COLOR),
        (low,  "Low",      LOW_COLOR),
    ]:
        if count > 0:
            data.append(count)
            labels.append(f"{label}\n{count}")
            clrs.append(clr)

    if not data:
        data   = [1]
        labels = ["No Gaps"]
        clrs   = [LOW_COLOR]

    d = Drawing(size, size)
    pie = Pie()
    pie.x = size * 0.1
    pie.y = size * 0.1
    pie.width  = size * 0.8
    pie.height = size * 0.8
    pie.data   = data
    pie.labels = labels
    pie.slices.strokeWidth  = 1
    pie.slices.strokeColor  = white
    pie.simpleLabels        = 0
    pie.sideLabels          = 1
    pie.innerRadiusFraction = 0.45  # donut hole

    for i, clr in enumerate(clrs):
        pie.slices[i].fillColor   = clr
        pie.slices[i].labelRadius = 1.25
        pie.slices[i].fontSize    = 7
        pie.slices[i].fontColor   = TEXT_MAIN

    d.add(pie)
    return d


# ── CIS IG1 control status table ─────────────────────────────────────────────

def _build_cis_table(gaps, styles):
    """Build a compact scorecard-style CIS IG1 control status table."""
    gap_names = {g["name"] for g in gaps}
    gap_tool_map = {g["name"]: (g.get("tool") or "—", g["priority"]) for g in gaps}

    hdr = [
        Paragraph("Control", styles["table_header"]),
        Paragraph("Description", styles["table_header"]),
        Paragraph("Status", styles["table_header"]),
        Paragraph("Recommended Tool", styles["table_header"]),
    ]
    rows = [hdr]

    for ctrl_id, ctrl_name in _CIS_DISPLAY:
        if ctrl_name in gap_names:
            _, priority = gap_tool_map[ctrl_name]
            tool_str = gap_tool_map[ctrl_name][0]
            if priority == "CRITICAL":
                status_p = Paragraph("FAIL", styles["fail_tag"])
            elif priority == "HIGH":
                status_p = Paragraph("FAIL", styles["warn_tag"])
            else:
                status_p = Paragraph("FAIL", styles["warn_tag"])
        else:
            status_p = Paragraph("PASS", styles["pass_tag"])
            tool_str = "—"

        rows.append([
            Paragraph(ctrl_id, styles["table_cell"]),
            Paragraph(ctrl_name, styles["table_cell"]),
            status_p,
            Paragraph(tool_str, styles["table_cell"]),
        ])

    col_widths = [0.55*inch, 2.3*inch, 0.6*inch, 2.25*inch]
    t = Table(rows, colWidths=col_widths, repeatRows=1)

    ts = [
        # Header
        ("BACKGROUND",    (0, 0), (-1, 0), BRAND_MID),
        ("TEXTCOLOR",     (0, 0), (-1, 0), white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1,  0), 8),
        ("ALIGN",         (0, 0), (-1,  0), "CENTER"),
        # Body
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.4, GRID_LINE),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (2, 1), (2, -1), "CENTER"),
    ]
    # Alternating row backgrounds
    for i in range(1, len(rows)):
        bg = white if i % 2 == 1 else SECTION_HDR
        ts.append(("BACKGROUND", (0, i), (-1, i), bg))

    t.setStyle(TableStyle(ts))
    return t


# ── Main report function ───────────────────────────────────────────────────────

def generate_report(output_path, company_token, scoring_result,
                    ai_risk_text, ai_pricing_text,
                    ai_compliance_text=None, ai_insurance_text=None,
                    report_date=None):
    """Build the full PDF report. Returns the output_path."""
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    styles = _build_styles()
    report_date = report_date or datetime.now().strftime("%B %d, %Y")

    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        topMargin=0.7*inch, bottomMargin=0.6*inch,
        leftMargin=0.75*inch, rightMargin=0.75*inch,
    )

    story = []

    # ── PAGE 1 ────────────────────────────────────────────────────────────────

    # Cover title bar (dark band, matching original branding)
    story.append(Spacer(1, 0.2*inch))
    cover_data = [[Paragraph("SECURITY ASSESSMENT REPORT", styles["title"])]]
    cover_table = Table(cover_data, colWidths=[7*inch])
    cover_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), BRAND_DARK),
        ("TOPPADDING",    (0, 0), (-1, -1), 16),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
    ]))
    story.append(cover_table)
    story.append(Spacer(1, 0.12*inch))

    # ── Scorecard header: two-column layout ──────────────────────────────────
    score = scoring_result.normalized_score
    score_color = (CRITICAL_COLOR if score >= 75 else HIGH_COLOR if score >= 55
                   else MEDIUM_COLOR if score >= 35 else LOW_COLOR)

    score_style = ParagraphStyle("ScoreDyn", fontSize=56, fontName="Helvetica-Bold",
                                  textColor=score_color, alignment=TA_CENTER, leading=60)
    tier_style  = ParagraphStyle("TierDyn", fontSize=11, fontName="Helvetica-Bold",
                                  textColor=BRAND_MID, alignment=TA_CENTER)
    lbl_style   = ParagraphStyle("LblDyn", fontSize=8, fontName="Helvetica",
                                  textColor=TEXT_MUTED, alignment=TA_CENTER)

    p = scoring_result.pricing_band

    left_col = [
        [Paragraph(str(score), score_style)],
        [Paragraph("RISK SCORE  /100", lbl_style)],
        [Spacer(1, 4)],
        [GaugeBar(score, width=2.6*inch)],
        [Spacer(1, 4)],
        [Paragraph(scoring_result.tier, tier_style)],
    ]
    left_tbl = Table(left_col, colWidths=[2.8*inch])
    left_tbl.setStyle(TableStyle([
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
    ]))

    meta_style = ParagraphStyle("MetaVal", fontSize=10, fontName="Helvetica",
                                 textColor=TEXT_MAIN, spaceAfter=4)
    meta_lbl   = ParagraphStyle("MetaLbl", fontSize=8, fontName="Helvetica",
                                 textColor=TEXT_MUTED, spaceAfter=1)

    right_col = [
        [Paragraph("Client Reference", meta_lbl), Paragraph(company_token, meta_style)],
        [Paragraph("Assessment Date",  meta_lbl), Paragraph(report_date,   meta_style)],
        [Paragraph("Pricing Range",    meta_lbl),
         Paragraph(f"${p['low']:,} – ${p['high']:,} / {p['period'].capitalize()}", meta_style)],
        [Paragraph("Risk Tier",        meta_lbl), Paragraph(scoring_result.tier, meta_style)],
    ]
    right_tbl = Table(right_col, colWidths=[1.3*inch, 2.8*inch])
    right_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
    ]))

    scorecard_tbl = Table(
        [[left_tbl, right_tbl]],
        colWidths=[2.9*inch, 4.1*inch],
    )
    scorecard_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), BRAND_LIGHT),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LINEAFTER",     (0, 0), (0, 0), 1, GRID_LINE),
    ]))
    story.append(scorecard_tbl)
    story.append(Spacer(1, 0.18*inch))

    # ── CIS IG1 control table + pie chart side-by-side ───────────────────────
    story.append(AccentHeader("CIS IG1 Control Status", bar_color=BRAND_MID))
    story.append(Spacer(1, 0.06*inch))

    cis_tbl  = _build_cis_table(scoring_result.control_gaps, styles)
    pie_draw = _build_gap_pie(scoring_result.control_gaps, size=150)

    # Wrap pie chart in a small label block
    pie_lbl = ParagraphStyle("PieLbl", fontSize=8, fontName="Helvetica-Bold",
                              textColor=TEXT_MUTED, alignment=TA_CENTER)
    pie_cell = Table(
        [[pie_draw], [Paragraph("Gap Distribution", pie_lbl)]],
        colWidths=[1.7*inch],
    )
    pie_cell.setStyle(TableStyle([
        ("ALIGN",   (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",  (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    combined = Table(
        [[cis_tbl, pie_cell]],
        colWidths=[5.7*inch, 1.7*inch],
    )
    combined.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",(0, 0), (-1, -1), 0),
        ("TOPPADDING",  (0, 0), (-1, -1), 0),
    ]))
    story.append(combined)
    story.append(Spacer(1, 0.1*inch))

    # ── Priority distribution summary row ─────────────────────────────────────
    crit_c = sum(1 for g in scoring_result.control_gaps if g["priority"] == "CRITICAL")
    high_c = sum(1 for g in scoring_result.control_gaps if g["priority"] == "HIGH")
    med_c  = sum(1 for g in scoring_result.control_gaps if g["priority"] == "MEDIUM")

    dist_style_base = dict(fontSize=9, fontName="Helvetica-Bold",
                           alignment=TA_CENTER, spaceAfter=0)
    crit_s = ParagraphStyle("CritDist", textColor=CRITICAL_COLOR, **dist_style_base)
    high_s = ParagraphStyle("HighDist", textColor=HIGH_COLOR, **dist_style_base)
    med_s  = ParagraphStyle("MedDist",  textColor=MEDIUM_COLOR, **dist_style_base)
    sep_s  = ParagraphStyle("SepDist",  textColor=TEXT_MUTED, fontSize=9,
                             fontName="Helvetica", alignment=TA_CENTER)

    dist_row = [[
        Paragraph(f"{crit_c} Critical", crit_s),
        Paragraph("|", sep_s),
        Paragraph(f"{high_c} High", high_s),
        Paragraph("|", sep_s),
        Paragraph(f"{med_c} Medium", med_s),
    ]]
    dist_tbl = Table(dist_row, colWidths=[1.4*inch, 0.3*inch, 1.0*inch, 0.3*inch, 1.0*inch])
    dist_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), SECTION_HDR),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("BOX",           (0, 0), (-1, -1), 0.5, GRID_LINE),
    ]))
    story.append(dist_tbl)

    if scoring_result.upsell:
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "This client profile aligns well with Tier 1 vCISO services.",
            ParagraphStyle("Upsell", fontSize=9, fontName="Helvetica-Oblique",
                           textColor=BRAND_ACCENT)
        ))

    story.append(PageBreak())

    # ── PAGE 2+: Risk Assessment ──────────────────────────────────────────────
    story.append(AccentHeader("Risk Assessment", bar_color=BRAND_ACCENT))
    story.append(Spacer(1, 0.1*inch))
    story.extend(_parse_ai_section(ai_risk_text, styles))
    story.append(Spacer(1, 0.15*inch))

    # Control Gap Summary (detailed)
    story.append(AccentHeader("Control Gap Summary", bar_color=BRAND_MID, font_size=11))
    story.append(Spacer(1, 0.06*inch))
    gap_data = [["Control", "Gap", "Priority", "Recommended Tool"]]
    for g in scoring_result.control_gaps:
        gap_data.append([g["control"], g["name"], g["priority"], g.get("tool") or "—"])

    gap_table = Table(gap_data, colWidths=[0.7*inch, 2.5*inch, 0.9*inch, 2.9*inch])
    gap_ts = [
        ("BACKGROUND",    (0, 0), (-1,  0), BRAND_DARK),
        ("TEXTCOLOR",     (0, 0), (-1,  0), white),
        ("FONTNAME",      (0, 0), (-1,  0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.4, GRID_LINE),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i in range(1, len(gap_data)):
        bg = white if i % 2 == 1 else SECTION_HDR
        gap_ts.append(("BACKGROUND", (0, i), (-1, i), bg))
    for i, g in enumerate(scoring_result.control_gaps, start=1):
        clr = PRIORITY_COLORS.get(g["priority"], TEXT_MUTED)
        gap_ts.append(("TEXTCOLOR", (2, i), (2, i), clr))
        gap_ts.append(("FONTNAME",  (2, i), (2, i), "Helvetica-Bold"))
    gap_table.setStyle(TableStyle(gap_ts))
    story.append(gap_table)
    story.append(PageBreak())

    # ── Pricing section ───────────────────────────────────────────────────────
    story.append(AccentHeader("Engagement Pricing", bar_color=BRAND_MID))
    story.append(Spacer(1, 0.08*inch))
    pricing_data = [
        ["Estimated Range", "Period", "Tier"],
        [f"${p['low']:,} – ${p['high']:,}", p["period"].capitalize(), scoring_result.tier],
    ]
    pricing_table = Table(pricing_data, colWidths=[3*inch, 2*inch, 2*inch])
    pricing_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1,  0), BRAND_MID),
        ("TEXTCOLOR",     (0, 0), (-1,  0), white),
        ("FONTNAME",      (0, 0), (-1,  0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [white, BRAND_LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.5, GRID_LINE),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
    ]))
    story.append(pricing_table)
    story.append(Spacer(1, 0.1*inch))
    story.extend(_parse_ai_section(ai_pricing_text, styles))

    # ── Recommended tools ─────────────────────────────────────────────────────
    story.append(Spacer(1, 0.1*inch))
    story.append(AccentHeader("Recommended Security Stack", bar_color=BRAND_MID))
    story.append(Spacer(1, 0.06*inch))
    for tool in scoring_result.recommended_tools:
        story.append(Paragraph(f"• {tool}", styles["body"]))
    story.append(Spacer(1, 0.15*inch))

    # ── Compliance ────────────────────────────────────────────────────────────
    if ai_compliance_text:
        story.append(PageBreak())
        story.append(AccentHeader("Compliance Gap Analysis", bar_color=BRAND_ACCENT))
        story.append(Spacer(1, 0.1*inch))
        story.extend(_parse_ai_section(ai_compliance_text, styles))

    # ── Insurance ─────────────────────────────────────────────────────────────
    if ai_insurance_text:
        story.append(PageBreak())
        story.append(AccentHeader("Cyber Insurance Readiness", bar_color=BRAND_ACCENT))
        story.append(Spacer(1, 0.1*inch))
        story.extend(_parse_ai_section(ai_insurance_text, styles))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return output_path


# ── AI text parser (unchanged) ────────────────────────────────────────────────

def _parse_ai_section(text: str, styles: dict) -> list:
    """Convert AI text output to a flat list of reportlab flowables."""
    flowables = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            flowables.append(Spacer(1, 6))
        elif line.startswith("## "):
            flowables.append(Paragraph(line[3:], styles["h2"]))
        elif line.startswith("# "):
            flowables.append(Paragraph(line[2:], styles["h1"]))
        elif line.startswith(("- ", "• ")):
            flowables.append(Paragraph(f"• {line[2:]}", styles["body"]))
        elif line.startswith("**") and line.endswith("**"):
            bold_s = ParagraphStyle("BoldInline", fontSize=10, fontName="Helvetica-Bold",
                                    textColor=TEXT_MAIN, spaceAfter=4)
            flowables.append(Paragraph(line.strip("*"), bold_s))
        else:
            flowables.append(Paragraph(line, styles["body"]))
    return flowables
