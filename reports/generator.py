"""
reports/generator.py

Generates branded PDF reports from AI-produced content + scoring data.
Uses reportlab Platypus for multi-page layout.
"""

import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable
)
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# ── Brand colors ──────────────────────────────────────────────────────────────
BRAND_DARK   = HexColor("#1a1f2e")   # dark navy
BRAND_ACCENT = HexColor("#e63946")   # red accent
BRAND_MID    = HexColor("#2d3561")   # mid blue
BRAND_LIGHT  = HexColor("#f1f3f5")   # light gray bg
TEXT_MAIN    = HexColor("#1a1f2e")
TEXT_MUTED   = HexColor("#6c757d")

CRITICAL_COLOR = HexColor("#dc3545")
HIGH_COLOR     = HexColor("#fd7e14")
MEDIUM_COLOR   = HexColor("#ffc107")
LOW_COLOR      = HexColor("#28a745")

PRIORITY_COLORS = {
    "CRITICAL": CRITICAL_COLOR,
    "HIGH":     HIGH_COLOR,
    "MEDIUM":   MEDIUM_COLOR,
    "LOW":      LOW_COLOR,
}


def _build_styles():
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "ReportTitle",
            fontSize=26, fontName="Helvetica-Bold",
            textColor=white, spaceAfter=6, alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            fontSize=13, fontName="Helvetica",
            textColor=HexColor("#adb5bd"), spaceAfter=4, alignment=TA_LEFT,
        ),
        "h1": ParagraphStyle(
            "H1", fontSize=16, fontName="Helvetica-Bold",
            textColor=BRAND_DARK, spaceBefore=20, spaceAfter=8,
            borderPad=4,
        ),
        "h2": ParagraphStyle(
            "H2", fontSize=13, fontName="Helvetica-Bold",
            textColor=BRAND_MID, spaceBefore=14, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "Body", fontSize=10, fontName="Helvetica",
            textColor=TEXT_MAIN, spaceAfter=8, leading=16,
        ),
        "muted": ParagraphStyle(
            "Muted", fontSize=9, fontName="Helvetica",
            textColor=TEXT_MUTED, spaceAfter=4,
        ),
        "table_header": ParagraphStyle(
            "TableHeader", fontSize=9, fontName="Helvetica-Bold",
            textColor=white, alignment=TA_CENTER,
        ),
        "table_cell": ParagraphStyle(
            "TableCell", fontSize=9, fontName="Helvetica",
            textColor=TEXT_MAIN, leading=13,
        ),
        "score_big": ParagraphStyle(
            "ScoreBig", fontSize=48, fontName="Helvetica-Bold",
            textColor=BRAND_ACCENT, alignment=TA_CENTER,
        ),
        "score_label": ParagraphStyle(
            "ScoreLabel", fontSize=11, fontName="Helvetica",
            textColor=TEXT_MUTED, alignment=TA_CENTER,
        ),
    }
    return styles


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


def generate_report(
    output_path: str,
    company_token: str,          # anonymized company identifier
    scoring_result,              # ScoringResult from scoring/engine.py
    ai_risk_text: str,
    ai_pricing_text: str,
    ai_compliance_text: str = None,
    ai_insurance_text: str = None,
    report_date: str = None,
) -> str:
    """
    Build the full PDF report. Returns the output_path.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    styles = _build_styles()
    report_date = report_date or datetime.now().strftime("%B %d, %Y")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        topMargin=0.7 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    story = []

    # ── Cover block ───────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.3 * inch))

    # Dark cover banner
    cover_data = [[
        Paragraph("SECURITY ASSESSMENT REPORT", styles["title"]),
    ]]
    cover_table = Table(cover_data, colWidths=[7 * inch])
    cover_table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), BRAND_DARK),
        ("TOPPADDING",  (0, 0), (-1, -1), 20),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 20),
        ("LEFTPADDING", (0, 0), (-1, -1), 24),
        ("ROUNDEDCORNERS", [8]),
    ]))
    story.append(cover_table)
    story.append(Spacer(1, 0.15 * inch))

    # Meta row
    meta_data = [[
        Paragraph(f"Client Reference: {company_token}", styles["muted"]),
        Paragraph(f"Date: {report_date}", styles["muted"]),
        Paragraph(f"Tier: {scoring_result.tier}", styles["muted"]),
    ]]
    meta_table = Table(meta_data, colWidths=[2.3 * inch, 2.3 * inch, 2.4 * inch])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), BRAND_LIGHT),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.3 * inch))

    # ── Risk score widget ─────────────────────────────────────────────────────
    score = scoring_result.normalized_score
    score_color = (CRITICAL_COLOR if score >= 75 else HIGH_COLOR if score >= 55
                   else MEDIUM_COLOR if score >= 35 else LOW_COLOR)

    score_style = ParagraphStyle(
        "ScoreDyn", fontSize=52, fontName="Helvetica-Bold",
        textColor=score_color, alignment=TA_CENTER,
    )
    score_data = [[
        Paragraph(str(score), score_style),
        Paragraph("/100", ParagraphStyle("Slash", fontSize=24, fontName="Helvetica",
                  textColor=TEXT_MUTED, alignment=TA_LEFT)),
        Paragraph(scoring_result.tier, ParagraphStyle("TierLabel", fontSize=13,
                  fontName="Helvetica-Bold", textColor=BRAND_MID, alignment=TA_CENTER)),
    ]]
    score_table = Table(score_data, colWidths=[1.2 * inch, 0.8 * inch, 5 * inch])
    score_table.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("BACKGROUND",    (0, 0), (-1, -1), BRAND_LIGHT),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("ROUNDEDCORNERS", [6]),
    ]))
    story.append(score_table)

    if scoring_result.upsell:
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            "⚡ This client's profile suggests strong value alignment with Tier 1 vCISO services.",
            ParagraphStyle("Upsell", fontSize=9, fontName="Helvetica-Oblique",
                           textColor=BRAND_ACCENT)
        ))

    story.append(Spacer(1, 0.25 * inch))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_LIGHT))
    story.append(Spacer(1, 0.15 * inch))

    # ── Pricing band ──────────────────────────────────────────────────────────
    p = scoring_result.pricing_band
    story.append(Paragraph("Engagement Pricing", styles["h1"]))
    pricing_data = [
        ["Estimated Range", "Period", "Tier"],
        [
            f"${p['low']:,} – ${p['high']:,}",
            p["period"].capitalize(),
            scoring_result.tier,
        ]
    ]
    pricing_table = Table(pricing_data, colWidths=[3 * inch, 2 * inch, 2 * inch])
    pricing_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), BRAND_MID),
        ("TEXTCOLOR",     (0, 0), (-1, 0), white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, BRAND_LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.5, HexColor("#dee2e6")),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
    ]))
    story.append(pricing_table)
    story.append(Spacer(1, 0.1 * inch))
    story.append(_parse_ai_text(ai_pricing_text, styles))

    story.append(PageBreak())

    # ── Risk Assessment ───────────────────────────────────────────────────────
    story.append(Paragraph("Risk Assessment", styles["h1"]))
    story.append(_parse_ai_text(ai_risk_text, styles))
    story.append(Spacer(1, 0.2 * inch))

    # ── Control Gaps Table ────────────────────────────────────────────────────
    story.append(Paragraph("Control Gap Summary", styles["h2"]))
    gap_data = [["Control", "Gap", "Priority", "Recommended Tool"]]
    for g in scoring_result.control_gaps:
        gap_data.append([
            g["control"],
            g["name"],
            g["priority"],
            g.get("tool") or "—",
        ])

    gap_table = Table(gap_data, colWidths=[0.8*inch, 2.5*inch, 1*inch, 2.7*inch])
    gap_styles = [
        ("BACKGROUND",    (0, 0), (-1, 0), BRAND_DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0), white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("GRID",          (0, 0), (-1, -1), 0.5, HexColor("#dee2e6")),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, BRAND_LIGHT]),
    ]
    # Color-code priority cells
    for i, g in enumerate(scoring_result.control_gaps, start=1):
        color = PRIORITY_COLORS.get(g["priority"], TEXT_MUTED)
        gap_styles.append(("TEXTCOLOR", (2, i), (2, i), color))
        gap_styles.append(("FONTNAME",  (2, i), (2, i), "Helvetica-Bold"))

    gap_table.setStyle(TableStyle(gap_styles))
    story.append(gap_table)

    story.append(PageBreak())

    # ── Recommended Tools ─────────────────────────────────────────────────────
    story.append(Paragraph("Recommended Security Stack", styles["h1"]))
    for tool in scoring_result.recommended_tools:
        story.append(Paragraph(f"• {tool}", styles["body"]))
    story.append(Spacer(1, 0.2 * inch))

    # ── Compliance section (conditional) ─────────────────────────────────────
    if ai_compliance_text:
        story.append(Paragraph("Compliance Gap Analysis", styles["h1"]))
        story.append(_parse_ai_text(ai_compliance_text, styles))
        story.append(PageBreak())

    # ── Insurance section (conditional) ──────────────────────────────────────
    if ai_insurance_text:
        story.append(Paragraph("Cyber Insurance Readiness", styles["h1"]))
        story.append(_parse_ai_text(ai_insurance_text, styles))

    # ── Build ─────────────────────────────────────────────────────────────────
    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return output_path


def _parse_ai_text(text: str, styles: dict):
    """
    Convert plain AI text output into reportlab flowables.
    Handles markdown-style headers and bullet points.
    """
    from reportlab.platypus import ListFlowable, ListItem
    flowables = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            flowables.append(Spacer(1, 6))
        elif line.startswith("## "):
            flowables.append(Paragraph(line[3:], styles["h2"]))
        elif line.startswith("# "):
            flowables.append(Paragraph(line[2:], styles["h1"]))
        elif line.startswith("- ") or line.startswith("• "):
            flowables.append(Paragraph(f"• {line[2:]}", styles["body"]))
        elif line.startswith("**") and line.endswith("**"):
            bold_style = ParagraphStyle("Bold", fontSize=10, fontName="Helvetica-Bold",
                                        textColor=TEXT_MAIN, spaceAfter=4)
            flowables.append(Paragraph(line.strip("*"), bold_style))
        else:
            flowables.append(Paragraph(line, styles["body"]))
    return flowables[0] if len(flowables) == 1 else _FlowableList(flowables)


class _FlowableList:
    """Wrapper to return multiple flowables from a single function."""
    def __init__(self, items):
        self.items = items

    def __iter__(self):
        return iter(self.items)


# Patch: make generate_report handle _FlowableList in story
_orig_generate = generate_report

def generate_report(output_path, company_token, scoring_result,
                    ai_risk_text, ai_pricing_text,
                    ai_compliance_text=None, ai_insurance_text=None,
                    report_date=None):
    """Wrapper that flattens _FlowableList items in the story."""
    import os
    from datetime import datetime

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    styles = _build_styles()
    report_date = report_date or datetime.now().strftime("%B %d, %Y")

    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        topMargin=0.7*inch, bottomMargin=0.6*inch,
        leftMargin=0.75*inch, rightMargin=0.75*inch,
    )

    raw_story = []

    # Cover
    raw_story.append(Spacer(1, 0.3*inch))
    cover_data = [[Paragraph("SECURITY ASSESSMENT REPORT", styles["title"])]]
    cover_table = Table(cover_data, colWidths=[7*inch])
    cover_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), BRAND_DARK),
        ("TOPPADDING", (0,0), (-1,-1), 20),
        ("BOTTOMPADDING", (0,0), (-1,-1), 20),
        ("LEFTPADDING", (0,0), (-1,-1), 24),
    ]))
    raw_story.append(cover_table)
    raw_story.append(Spacer(1, 0.15*inch))

    meta_data = [[
        Paragraph(f"Client Reference: {company_token}", styles["muted"]),
        Paragraph(f"Date: {report_date}", styles["muted"]),
        Paragraph(f"Tier: {scoring_result.tier}", styles["muted"]),
    ]]
    meta_table = Table(meta_data, colWidths=[2.3*inch, 2.3*inch, 2.4*inch])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), BRAND_LIGHT),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
    ]))
    raw_story.append(meta_table)
    raw_story.append(Spacer(1, 0.25*inch))

    # Score widget
    score = scoring_result.normalized_score
    score_color = (CRITICAL_COLOR if score >= 75 else HIGH_COLOR if score >= 55
                   else MEDIUM_COLOR if score >= 35 else LOW_COLOR)
    score_style = ParagraphStyle("ScoreDyn", fontSize=52, fontName="Helvetica-Bold",
                                  textColor=score_color, alignment=TA_CENTER)
    score_data = [[
        Paragraph(str(score), score_style),
        Paragraph("/100", ParagraphStyle("Slash", fontSize=24, fontName="Helvetica",
                  textColor=TEXT_MUTED, alignment=TA_LEFT)),
        Paragraph(scoring_result.tier, ParagraphStyle("TierLabel", fontSize=13,
                  fontName="Helvetica-Bold", textColor=BRAND_MID, alignment=TA_CENTER)),
    ]]
    score_table = Table(score_data, colWidths=[1.2*inch, 0.8*inch, 5*inch])
    score_table.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("BACKGROUND", (0,0), (-1,-1), BRAND_LIGHT),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
    ]))
    raw_story.append(score_table)

    if scoring_result.upsell:
        raw_story.append(Spacer(1, 8))
        raw_story.append(Paragraph(
            "This client profile aligns well with Tier 1 vCISO services.",
            ParagraphStyle("Upsell", fontSize=9, fontName="Helvetica-Oblique", textColor=BRAND_ACCENT)
        ))

    raw_story.append(Spacer(1, 0.2*inch))
    raw_story.append(HRFlowable(width="100%", thickness=1, color=BRAND_LIGHT))
    raw_story.append(Spacer(1, 0.15*inch))

    # Pricing
    p = scoring_result.pricing_band
    raw_story.append(Paragraph("Engagement Pricing", styles["h1"]))
    pricing_data = [
        ["Estimated Range", "Period", "Tier"],
        [f"${p['low']:,} – ${p['high']:,}", p["period"].capitalize(), scoring_result.tier],
    ]
    pricing_table = Table(pricing_data, colWidths=[3*inch, 2*inch, 2*inch])
    pricing_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), BRAND_MID),
        ("TEXTCOLOR",  (0,0), (-1,0), white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 10),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [white, BRAND_LIGHT]),
        ("GRID",       (0,0), (-1,-1), 0.5, HexColor("#dee2e6")),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
    ]))
    raw_story.append(pricing_table)
    raw_story.append(Spacer(1, 0.1*inch))
    raw_story.extend(_parse_ai_section(ai_pricing_text, styles))

    raw_story.append(PageBreak())

    # Risk Assessment
    raw_story.append(Paragraph("Risk Assessment", styles["h1"]))
    raw_story.extend(_parse_ai_section(ai_risk_text, styles))
    raw_story.append(Spacer(1, 0.2*inch))

    # Gaps table
    raw_story.append(Paragraph("Control Gap Summary", styles["h2"]))
    gap_data = [["Control", "Gap", "Priority", "Recommended Tool"]]
    for g in scoring_result.control_gaps:
        gap_data.append([g["control"], g["name"], g["priority"], g.get("tool") or "—"])

    gap_table = Table(gap_data, colWidths=[0.8*inch, 2.5*inch, 1*inch, 2.7*inch])
    gap_ts = [
        ("BACKGROUND",  (0,0), (-1,0), BRAND_DARK),
        ("TEXTCOLOR",   (0,0), (-1,0), white),
        ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,-1), 9),
        ("GRID",        (0,0), (-1,-1), 0.5, HexColor("#dee2e6")),
        ("TOPPADDING",  (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [white, BRAND_LIGHT]),
    ]
    for i, g in enumerate(scoring_result.control_gaps, start=1):
        color = PRIORITY_COLORS.get(g["priority"], TEXT_MUTED)
        gap_ts.append(("TEXTCOLOR", (2,i), (2,i), color))
        gap_ts.append(("FONTNAME",  (2,i), (2,i), "Helvetica-Bold"))
    gap_table.setStyle(TableStyle(gap_ts))
    raw_story.append(gap_table)
    raw_story.append(PageBreak())

    # Tools
    raw_story.append(Paragraph("Recommended Security Stack", styles["h1"]))
    for tool in scoring_result.recommended_tools:
        raw_story.append(Paragraph(f"• {tool}", styles["body"]))
    raw_story.append(Spacer(1, 0.2*inch))

    # Compliance
    if ai_compliance_text:
        raw_story.append(Paragraph("Compliance Gap Analysis", styles["h1"]))
        raw_story.extend(_parse_ai_section(ai_compliance_text, styles))
        raw_story.append(PageBreak())

    # Insurance
    if ai_insurance_text:
        raw_story.append(Paragraph("Cyber Insurance Readiness", styles["h1"]))
        raw_story.extend(_parse_ai_section(ai_insurance_text, styles))

    doc.build(raw_story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return output_path


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
