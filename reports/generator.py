"""
reports/generator.py

Qualys-style scorecard PDF:
- Letter grade + stats panel on page 1
- Horizontal bar chart of control completion
- Gap table with partial credit shown
- AI-written sections
- Branded header/footer
"""

import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white, black, Color
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics import renderPDF
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# ── Brand palette ─────────────────────────────────────────────────────────────
BRAND_DARK   = HexColor("#1a1f2e")
BRAND_MID    = HexColor("#2d3561")
BRAND_ACCENT = HexColor("#e63946")
BRAND_LIGHT  = HexColor("#f1f3f5")
BRAND_BLUE   = HexColor("#7c8cf8")
TEXT_MAIN    = HexColor("#1a1f2e")
TEXT_MUTED   = HexColor("#6c757d")
TEXT_WHITE   = white

GRADE_COLORS = {
    "A": HexColor("#2d6a4f"),
    "B": HexColor("#52b788"),
    "C": HexColor("#f4a261"),
    "D": HexColor("#e76f51"),
    "F": HexColor("#c1121f"),
}
PRIORITY_COLORS = {
    "CRITICAL": HexColor("#c1121f"),
    "HIGH":     HexColor("#e76f51"),
    "MEDIUM":   HexColor("#f4a261"),
    "LOW":      HexColor("#52b788"),
}
BAR_COLORS = {
    "high":   HexColor("#e63946"),
    "mid":    HexColor("#f4a261"),
    "low":    HexColor("#52b788"),
}


def _styles():
    s = {
        "h1": ParagraphStyle("H1", fontSize=15, fontName="Helvetica-Bold",
                              textColor=BRAND_DARK, spaceBefore=18, spaceAfter=8),
        "h2": ParagraphStyle("H2", fontSize=12, fontName="Helvetica-Bold",
                              textColor=BRAND_MID, spaceBefore=12, spaceAfter=6),
        "body": ParagraphStyle("Body", fontSize=9.5, fontName="Helvetica",
                                textColor=TEXT_MAIN, spaceAfter=6, leading=15),
        "muted": ParagraphStyle("Muted", fontSize=8.5, fontName="Helvetica",
                                 textColor=TEXT_MUTED, spaceAfter=4),
        "label": ParagraphStyle("Label", fontSize=8, fontName="Helvetica-Bold",
                                 textColor=TEXT_MUTED, spaceAfter=2,
                                 textTransform="uppercase"),
        "stat_val": ParagraphStyle("StatVal", fontSize=22, fontName="Helvetica-Bold",
                                    textColor=BRAND_DARK, spaceAfter=0, leading=26),
        "stat_lbl": ParagraphStyle("StatLbl", fontSize=8, fontName="Helvetica",
                                    textColor=TEXT_MUTED, spaceAfter=8),
        "title": ParagraphStyle("Title", fontSize=22, fontName="Helvetica-Bold",
                                  textColor=white, spaceAfter=4),
        "subtitle": ParagraphStyle("Subtitle", fontSize=11, fontName="Helvetica",
                                    textColor=HexColor("#adb5bd"), spaceAfter=0),
    }
    return s


def _header_footer(canvas, doc):
    canvas.saveState()
    w, h = letter
    # Header
    canvas.setFillColor(BRAND_DARK)
    canvas.rect(0, h - 0.45*inch, w, 0.45*inch, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(0.5*inch, h - 0.28*inch, "CONFIDENTIAL — MSSP SECURITY ASSESSMENT")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(w - 0.5*inch, h - 0.28*inch, datetime.now().strftime("%B %d, %Y"))
    # Accent line
    canvas.setFillColor(BRAND_ACCENT)
    canvas.rect(0, h - 0.48*inch, w, 0.03*inch, fill=1, stroke=0)
    # Footer
    canvas.setFillColor(BRAND_LIGHT)
    canvas.rect(0, 0, w, 0.35*inch, fill=1, stroke=0)
    canvas.setFillColor(TEXT_MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(0.5*inch, 0.12*inch,
        "This report is confidential and intended solely for the named recipient.")
    canvas.drawRightString(w - 0.5*inch, 0.12*inch, f"Page {doc.page}")
    canvas.restoreState()


def _grade_block(grade: str, score: int) -> Drawing:
    """Large letter grade box with score — left side of scorecard."""
    d = Drawing(1.1*inch, 1.1*inch)
    color = GRADE_COLORS.get(grade, HexColor("#6c757d"))
    d.add(Rect(0, 0, 1.1*inch, 1.1*inch, fillColor=color, strokeColor=None))
    d.add(String(0.55*inch, 0.38*inch, grade,
                 fontName="Helvetica-Bold", fontSize=52,
                 fillColor=white, textAnchor="middle"))
    return d


def _horizontal_bar_chart(control_scores: list, width: float, height: float) -> Drawing:
    """
    Horizontal bar chart of CIS control completion percentages.
    Green = 80%+, orange = 40-79%, red = <40%
    """
    bar_h    = 14
    gap      = 6
    label_w  = 80
    bar_area = width - label_w - 50  # 50 for % label
    n        = len(control_scores)
    total_h  = n * (bar_h + gap) + 20

    d = Drawing(width, total_h)

    for i, ctrl in enumerate(control_scores):
        y = total_h - (i + 1) * (bar_h + gap)
        pct = ctrl["completion"]

        # Background track
        d.add(Rect(label_w, y, bar_area, bar_h,
                   fillColor=HexColor("#e9ecef"), strokeColor=None))
        # Fill bar
        fill_w = max(bar_area * pct / 100, 2)
        bar_color = (BAR_COLORS["low"] if pct >= 80
                     else BAR_COLORS["mid"] if pct >= 40
                     else BAR_COLORS["high"])
        d.add(Rect(label_w, y, fill_w, bar_h,
                   fillColor=bar_color, strokeColor=None))
        # Label
        short_name = ctrl["name"][:18] + ("…" if len(ctrl["name"]) > 18 else "")
        d.add(String(label_w - 4, y + 3, short_name,
                     fontName="Helvetica", fontSize=7.5,
                     fillColor=TEXT_MUTED.hexval() if hasattr(TEXT_MUTED, 'hexval') else "#6c757d",
                     textAnchor="end"))
        # Percentage label
        d.add(String(label_w + bar_area + 4, y + 3, f"{pct}%",
                     fontName="Helvetica-Bold", fontSize=7.5,
                     fillColor=bar_color.hexval() if hasattr(bar_color, 'hexval') else "#000000"))

    return d


def _stat_cell(label: str, value: str, styles) -> list:
    return [
        Paragraph(value, styles["stat_val"]),
        Paragraph(label, styles["stat_lbl"]),
    ]


def _parse_ai_section(text: str, styles: dict) -> list:
    flowables = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            flowables.append(Spacer(1, 5))
        elif line.startswith("## "):
            flowables.append(Paragraph(line[3:], styles["h2"]))
        elif line.startswith("# "):
            flowables.append(Paragraph(line[2:], styles["h1"]))
        elif line.startswith(("- ", "• ")):
            flowables.append(Paragraph(f"• {line[2:]}", styles["body"]))
        elif line.startswith("**") and line.endswith("**"):
            s = ParagraphStyle("BoldLine", fontSize=9.5, fontName="Helvetica-Bold",
                               textColor=TEXT_MAIN, spaceAfter=4)
            flowables.append(Paragraph(line.strip("*"), s))
        else:
            flowables.append(Paragraph(line, styles["body"]))
    return flowables


def generate_report(
    output_path: str,
    company_token: str,
    scoring_result,
    ai_risk_text: str,
    ai_pricing_text: str,
    ai_compliance_text: str = None,
    ai_insurance_text: str = None,
    report_date: str = None,
) -> str:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    styles = _styles()
    report_date = report_date or datetime.now().strftime("%B %d, %Y")
    W = 7.0 * inch   # usable width

    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        topMargin=0.6*inch, bottomMargin=0.5*inch,
        leftMargin=0.75*inch, rightMargin=0.75*inch,
    )

    story = []

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 1 — SCORECARD
    # ══════════════════════════════════════════════════════════════════════════

    # ── Title banner ──────────────────────────────────────────────────────────
    banner_data = [[
        Paragraph("SECURITY ASSESSMENT REPORT", styles["title"]),
        Paragraph(f"Site: {company_token}", styles["subtitle"]),
    ]]
    banner = Table(banner_data, colWidths=[W])
    banner.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), BRAND_DARK),
        ("TOPPADDING",    (0,0), (-1,-1), 16),
        ("BOTTOMPADDING", (0,0), (-1,-1), 16),
        ("LEFTPADDING",   (0,0), (-1,-1), 20),
    ]))
    story.append(banner)
    story.append(Spacer(1, 0.18*inch))

    # ── Grade + stats row ─────────────────────────────────────────────────────
    grade   = scoring_result.letter_grade
    score   = scoring_result.normalized_score
    ec      = 0  # not stored on result, pulled from summary
    n_gaps  = len(scoring_result.control_gaps)
    n_crit  = sum(1 for g in scoring_result.control_gaps if g["priority"] == "CRITICAL")
    n_ctrl  = len(scoring_result.control_scores)
    n_full  = sum(1 for c in scoring_result.control_scores if c["completion"] == 100)

    grade_drawing = _grade_block(grade, score)

    # Grade description
    grade_desc = {
        "A": "Excellent security posture. Minor gaps only.",
        "B": "Good posture with some areas for improvement.",
        "C": "Moderate risk. Several controls need attention.",
        "D": "Significant gaps. Immediate remediation advised.",
        "F": "Critical risk. Urgent action required.",
    }.get(grade, "")

    grade_cell = [
        [grade_drawing],
        [Paragraph(f"Grade {grade}", ParagraphStyle("GradeLabel", fontSize=11,
                   fontName="Helvetica-Bold", textColor=GRADE_COLORS.get(grade, TEXT_MUTED)))],
        [Paragraph(grade_desc, styles["muted"])],
    ]
    grade_tbl = Table(grade_cell, colWidths=[1.3*inch])
    grade_tbl.setStyle(TableStyle([
        ("ALIGN",   (0,0), (-1,-1), "CENTER"),
        ("VALIGN",  (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))

    # Stats cells
    def stat(val, lbl):
        return [Paragraph(str(val), styles["stat_val"]),
                Paragraph(lbl, styles["stat_lbl"])]

    p = scoring_result.pricing_band
    price_str = f"${p['low']//1000}k–${p['high']//1000}k" if p["period"] == "annual" \
                else f"${p['low']:,}/mo"

    stats_data = [[
        stat(f"{score}/100",   "Risk Score"),
        stat(f"{n_full}/{n_ctrl}", "Controls\nImplemented"),
        stat(str(n_crit),      "Critical\nGaps"),
        stat(scoring_result.tier.split(" - ")[1] if " - " in scoring_result.tier
             else scoring_result.tier, "Recommended\nTier"),
        stat(price_str,        "Estimated\nEngagement"),
    ]]
    stats_tbl = Table(stats_data, colWidths=[1.1*inch]*5)
    stats_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), BRAND_LIGHT),
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LINEAFTER",     (0,0), (-2,-1), 0.5, HexColor("#dee2e6")),
    ]))

    # Combine grade + stats
    scorecard_data = [[grade_tbl, stats_tbl]]
    scorecard = Table(scorecard_data, colWidths=[1.5*inch, 5.5*inch])
    scorecard.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("BACKGROUND",    (0,0), (0,-1), BRAND_LIGHT),
        ("LEFTPADDING",   (0,0), (0,-1), 10),
        ("RIGHTPADDING",  (0,0), (0,-1), 10),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))
    story.append(scorecard)
    story.append(Spacer(1, 0.2*inch))

    # ── Summary text (from scoring engine) ───────────────────────────────────
    story.append(Paragraph(scoring_result.summary, styles["body"]))
    story.append(Spacer(1, 0.1*inch))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BRAND_LIGHT))
    story.append(Spacer(1, 0.1*inch))

    # ── CIS Control Completion chart ──────────────────────────────────────────
    story.append(Paragraph("CIS IG1 Control Completion", styles["h1"]))

    chart = _horizontal_bar_chart(scoring_result.control_scores, W, 20)
    story.append(chart)
    story.append(Spacer(1, 0.1*inch))

    # Legend
    legend_data = [[
        Paragraph("■ 80–100%  Implemented", ParagraphStyle("Leg", fontSize=8,
                  fontName="Helvetica", textColor=BAR_COLORS["low"])),
        Paragraph("■ 40–79%  Partial", ParagraphStyle("Leg2", fontSize=8,
                  fontName="Helvetica", textColor=BAR_COLORS["mid"])),
        Paragraph("■ 0–39%  Gap / Missing", ParagraphStyle("Leg3", fontSize=8,
                  fontName="Helvetica", textColor=BAR_COLORS["high"])),
    ]]
    legend = Table(legend_data, colWidths=[W/3]*3)
    legend.setStyle(TableStyle([("ALIGN", (0,0), (-1,-1), "CENTER")]))
    story.append(legend)

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 2 — GAP TABLE + AI RISK ASSESSMENT
    # ══════════════════════════════════════════════════════════════════════════

    story.append(Paragraph("Control Gap Detail", styles["h1"]))

    # Vulnerability-style summary bar (like Qualys assets-by-vulnerability)
    total_gaps = len(scoring_result.control_gaps)
    if total_gaps > 0:
        breakdown = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for g in scoring_result.control_gaps:
            breakdown[g["priority"]] = breakdown.get(g["priority"], 0) + 1

        bar_w = W
        bar_h_px = 18
        sev_drawing = Drawing(bar_w, bar_h_px + 20)
        x = 0
        for priority, color in [("CRITICAL", PRIORITY_COLORS["CRITICAL"]),
                                  ("HIGH",     PRIORITY_COLORS["HIGH"]),
                                  ("MEDIUM",   PRIORITY_COLORS["MEDIUM"]),
                                  ("LOW",      PRIORITY_COLORS["LOW"])]:
            count = breakdown.get(priority, 0)
            if count == 0:
                continue
            seg_w = bar_w * count / total_gaps
            sev_drawing.add(Rect(x, bar_h_px, seg_w, bar_h_px,
                                  fillColor=color, strokeColor=None))
            if seg_w > 30:
                sev_drawing.add(String(x + seg_w/2, bar_h_px + 5,
                                        f"{count} {priority}",
                                        fontName="Helvetica-Bold", fontSize=7,
                                        fillColor=white, textAnchor="middle"))
            x += seg_w
        story.append(sev_drawing)
        story.append(Spacer(1, 0.12*inch))

    # Gap table
    gap_header = ["Control", "Name", "Complete", "Priority", "Missing Safeguards", "Tool"]
    gap_rows = [gap_header]
    for g in scoring_result.control_gaps:
        missing_text = "\n".join(f"• {m}" for m in g.get("missing", [])[:3])
        if len(g.get("missing", [])) > 3:
            missing_text += f"\n  (+{len(g['missing'])-3} more)"
        gap_rows.append([
            g["control"],
            g["name"],
            f"{g['completion']}%",
            g["priority"],
            missing_text or "—",
            g.get("tool") or "—",
        ])

    gap_tbl = Table(gap_rows, colWidths=[0.6*inch, 1.1*inch, 0.6*inch, 0.7*inch, 2.5*inch, 1.45*inch])
    gap_ts = [
        ("BACKGROUND",    (0,0), (-1,0), BRAND_DARK),
        ("TEXTCOLOR",     (0,0), (-1,0), white),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 7.5),
        ("GRID",          (0,0), (-1,-1), 0.4, HexColor("#dee2e6")),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [white, BRAND_LIGHT]),
    ]
    for i, g in enumerate(scoring_result.control_gaps, start=1):
        color = PRIORITY_COLORS.get(g["priority"], TEXT_MUTED)
        gap_ts.append(("TEXTCOLOR",  (3,i), (3,i), color))
        gap_ts.append(("FONTNAME",   (3,i), (3,i), "Helvetica-Bold"))
        # Completion % color
        comp = g["completion"]
        comp_color = (BAR_COLORS["low"] if comp >= 80
                      else BAR_COLORS["mid"] if comp >= 40
                      else BAR_COLORS["high"])
        gap_ts.append(("TEXTCOLOR", (2,i), (2,i), comp_color))
        gap_ts.append(("FONTNAME",  (2,i), (2,i), "Helvetica-Bold"))

    gap_tbl.setStyle(TableStyle(gap_ts))
    story.append(gap_tbl)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 3 — AI RISK ASSESSMENT
    # ══════════════════════════════════════════════════════════════════════════

    story.append(Paragraph("Risk Assessment", styles["h1"]))
    story.extend(_parse_ai_section(ai_risk_text, styles))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 4 — PRICING + RECOMMENDED STACK
    # ══════════════════════════════════════════════════════════════════════════

    story.append(Paragraph("Engagement Pricing", styles["h1"]))

    p = scoring_result.pricing_band
    pricing_rows = [
        ["Estimated Range", "Period", "Recommended Tier"],
        [f"${p['low']:,} – ${p['high']:,}", p["period"].capitalize(), scoring_result.tier],
    ]
    ptbl = Table(pricing_rows, colWidths=[2.5*inch, 1.5*inch, 3*inch])
    ptbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), BRAND_MID),
        ("TEXTCOLOR",     (0,0), (-1,0), white),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 9.5),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [white, BRAND_LIGHT]),
        ("GRID",          (0,0), (-1,-1), 0.5, HexColor("#dee2e6")),
        ("TOPPADDING",    (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
    ]))
    story.append(ptbl)
    story.append(Spacer(1, 0.15*inch))
    story.extend(_parse_ai_section(ai_pricing_text, styles))

    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph("Recommended Security Stack", styles["h1"]))
    tool_rows = [["Tool", "Purpose"]]
    tool_purposes = {
        "Huntress": "EDR + 24/7 Managed SOC — threat detection and response",
        "Ironscales": "AI-powered email security and phishing protection",
        "Qualys": "Continuous vulnerability scanning and patch tracking",
        "Duo": "MFA and zero-trust access control",
        "Okta": "Identity management and MFA",
        "Todyl": "Edge security, UTM, and SD-WAN",
    }
    for tool in scoring_result.recommended_tools:
        purpose = next((v for k, v in tool_purposes.items() if k in tool), "Security control")
        tool_rows.append([tool, purpose])

    ttbl = Table(tool_rows, colWidths=[2.8*inch, 4.2*inch])
    ttbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), BRAND_DARK),
        ("TEXTCOLOR",     (0,0), (-1,0), white),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 9),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [white, BRAND_LIGHT]),
        ("GRID",          (0,0), (-1,-1), 0.5, HexColor("#dee2e6")),
        ("TOPPADDING",    (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
    ]))
    story.append(ttbl)

    if scoring_result.upsell:
        story.append(Spacer(1, 0.15*inch))
        upsell_data = [[Paragraph(
            "⚡  This client's risk profile and compliance exposure align well with "
            "Tier 1 vCISO services. Consider presenting the full vCISO program.",
            ParagraphStyle("Upsell", fontSize=9, fontName="Helvetica-Oblique",
                           textColor=BRAND_ACCENT)
        )]]
        utbl = Table(upsell_data, colWidths=[W])
        utbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), HexColor("#fff3f3")),
            ("LEFTPADDING",   (0,0), (-1,-1), 14),
            ("TOPPADDING",    (0,0), (-1,-1), 10),
            ("BOTTOMPADDING", (0,0), (-1,-1), 10),
            ("BOX",           (0,0), (-1,-1), 1, BRAND_ACCENT),
        ]))
        story.append(utbl)

    # ── Compliance / Insurance (conditional) ──────────────────────────────────
    if ai_compliance_text:
        story.append(PageBreak())
        story.append(Paragraph("Compliance Gap Analysis", styles["h1"]))
        story.extend(_parse_ai_section(ai_compliance_text, styles))

    if ai_insurance_text:
        story.append(PageBreak())
        story.append(Paragraph("Cyber Insurance Readiness", styles["h1"]))
        story.extend(_parse_ai_section(ai_insurance_text, styles))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return output_path
