"""
web/app.py

Flask web app:
- Intake survey form (local only, not internet-facing)
- Anonymizer pipeline
- Scoring engine
- AI report generation
- PDF output
"""

import os
import sys
import uuid
import json
from datetime import datetime
from flask import Flask, render_template_string, request, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename

# Ensure the mssp/ root is on the path regardless of how the script is invoked
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from anonymizer.pipeline import Anonymizer
from scoring.engine import score_intake
from ai.backend import query
from ai.prompts import (
    risk_assessment_prompt,
    pricing_justification_prompt,
    compliance_gap_prompt,
    insurance_baseline_prompt,
)
from reports.generator import generate_report

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT, ".env"))

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    raise ValueError("FLASK_SECRET_KEY not set in .env")

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "../data/reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


# ── HTML Templates ─────────────────────────────────────────────────────────────

FORM_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Client Security Intake</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #0f1117; color: #e0e0e0; padding: 40px 20px; }
        .container { max-width: 720px; margin: 0 auto; }
        h1 { color: #fff; font-size: 24px; margin-bottom: 6px; }
        .subtitle { color: #6c757d; font-size: 14px; margin-bottom: 32px; }
        .section { background: #1a1f2e; border-radius: 10px; padding: 24px;
                   margin-bottom: 20px; border: 1px solid #2d3561; }
        .section h2 { color: #7c8cf8; font-size: 14px; text-transform: uppercase;
                      letter-spacing: 1px; margin-bottom: 18px; }
        .field { margin-bottom: 16px; }
        label { display: block; font-size: 13px; color: #adb5bd; margin-bottom: 6px; }
        input[type=text], input[type=number], select {
            width: 100%; padding: 10px 14px; background: #0f1117;
            border: 1px solid #2d3561; border-radius: 6px; color: #e0e0e0;
            font-size: 14px; }
        input:focus, select:focus { outline: none; border-color: #7c8cf8; }
        .checkbox-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .check-item { display: flex; align-items: center; gap: 8px; font-size: 13px;
                      color: #e0e0e0; cursor: pointer; }
        input[type=checkbox] { width: 16px; height: 16px; accent-color: #7c8cf8; }
        .range-label { display: flex; justify-content: space-between;
                       font-size: 11px; color: #6c757d; margin-top: 4px; }
        button[type=submit] {
            width: 100%; padding: 14px; background: #e63946; color: white;
            border: none; border-radius: 8px; font-size: 16px; font-weight: 600;
            cursor: pointer; margin-top: 10px; }
        button[type=submit]:hover { background: #c1121f; }
        .flash { background: #2d3561; color: #e0e0e0; padding: 12px 16px;
                 border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #e63946; }
        .disclaimer { color: #6c757d; font-size: 11px; text-align: center;
                      margin-top: 20px; }
    </style>
</head>
<body>
<div class="container">
    <h1>Client Security Intake</h1>
    <p class="subtitle">All data is anonymized before AI processing. Nothing leaves this machine.</p>

    {% for msg in get_flashed_messages() %}
    <div class="flash">{{ msg }}</div>
    {% endfor %}

    <form method="POST" action="/submit">
        <div class="section">
            <h2>Organization</h2>
            <div class="field">
                <label>Company Name (used for report reference only)</label>
                <input type="text" name="company_name" placeholder="Acme Corp" required>
            </div>
            <div class="field">
                <label>Industry Vertical</label>
                <select name="vertical">
                    <option value="healthcare">Healthcare</option>
                    <option value="finance">Finance / Banking</option>
                    <option value="legal">Legal</option>
                    <option value="technology">Technology</option>
                    <option value="retail">Retail</option>
                    <option value="education">Education</option>
                    <option value="manufacturing">Manufacturing</option>
                    <option value="nonprofit">Non-Profit</option>
                    <option value="government">Government / Public Sector</option>
                    <option value="other" selected>Other</option>
                </select>
            </div>
            <div class="field">
                <label>Number of Employees</label>
                <input type="number" name="employee_count" min="1" max="500" value="50" required>
            </div>
            <div class="field">
                <label>Remote Workforce % (0 = fully on-site, 100 = fully remote)</label>
                <input type="number" name="remote_work_pct" min="0" max="100" value="20">
                <div class="range-label"><span>0% On-site</span><span>100% Remote</span></div>
            </div>
        </div>

        <div class="section">
            <h2>Environment</h2>
            <div class="checkbox-grid">
                <label class="check-item">
                    <input type="checkbox" name="cloud_heavy"> Heavy cloud usage (M365/Google/AWS)
                </label>
                <label class="check-item">
                    <input type="checkbox" name="single_site"> Single physical location
                </label>
            </div>
        </div>

        <div class="section">
            <h2>Current Security Controls</h2>
            <p style="color:#6c757d; font-size:12px; margin-bottom:14px;">
                Check all that are currently in place and actively managed.
            </p>
            <div class="checkbox-grid">
                <label class="check-item">
                    <input type="checkbox" name="has_ad"> Centralized identity (AD / Entra)
                </label>
                <label class="check-item">
                    <input type="checkbox" name="has_mfa"> Multi-Factor Authentication (MFA)
                </label>
                <label class="check-item">
                    <input type="checkbox" name="has_edr"> EDR / Endpoint protection
                </label>
                <label class="check-item">
                    <input type="checkbox" name="has_vuln_mgmt"> Vulnerability scanning
                </label>
                <label class="check-item">
                    <input type="checkbox" name="has_email_security"> Email security / anti-phish
                </label>
                <label class="check-item">
                    <input type="checkbox" name="has_network_monitoring"> Network monitoring
                </label>
                <label class="check-item">
                    <input type="checkbox" name="has_sat"> Security awareness training
                </label>
                <label class="check-item">
                    <input type="checkbox" name="has_app_allowlisting"> Application allowlisting
                </label>
                <label class="check-item">
                    <input type="checkbox" name="has_backup"> Tested data backup / recovery
                </label>
                <label class="check-item">
                    <input type="checkbox" name="has_secure_config"> Hardened device configs
                </label>
                <label class="check-item">
                    <input type="checkbox" name="has_dlp"> Data loss prevention (DLP)
                </label>
                <label class="check-item">
                    <input type="checkbox" name="has_ir_plan"> Incident response plan
                </label>
                <label class="check-item">
                    <input type="checkbox" name="has_asset_inventory"> Asset inventory
                </label>
                <label class="check-item">
                    <input type="checkbox" name="has_software_inventory"> Software inventory
                </label>
            </div>
        </div>

        <div class="section">
            <h2>Compliance Requirements</h2>
            <div class="checkbox-grid">
                <label class="check-item">
                    <input type="checkbox" name="needs_hipaa"> HIPAA
                </label>
                <label class="check-item">
                    <input type="checkbox" name="needs_soc2"> SOC 2 Type II
                </label>
            </div>
        </div>

        <button type="submit">Generate Security Assessment Report</button>
    </form>
    <p class="disclaimer">Reports are stored locally. Client data is anonymized before AI processing.</p>
</div>
</body>
</html>
"""

PROCESSING_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Generating Report...</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #0f1117;
               color: #e0e0e0; display: flex; align-items: center;
               justify-content: center; min-height: 100vh; }
        .card { text-align: center; background: #1a1f2e; padding: 48px;
                border-radius: 12px; border: 1px solid #2d3561; max-width: 400px; }
        .spinner { width: 48px; height: 48px; border: 4px solid #2d3561;
                   border-top-color: #e63946; border-radius: 50%;
                   animation: spin 0.8s linear infinite; margin: 0 auto 24px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        h2 { color: #fff; margin-bottom: 8px; }
        p  { color: #6c757d; font-size: 14px; }
    </style>
    <meta http-equiv="refresh" content="2;url={{ url }}">
</head>
<body>
<div class="card">
    <div class="spinner"></div>
    <h2>Generating Report</h2>
    <p>Anonymizing data, scoring risks, and generating your PDF...</p>
</div>
</body>
</html>
"""


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(FORM_HTML)


@app.route("/submit", methods=["POST"])
def submit():
    session_id = str(uuid.uuid4())
    company_name = request.form.get("company_name", "Client")

    # Build intake dict from form
    intake_raw = {
        "company_name":       company_name,
        "vertical":           request.form.get("vertical", "other"),
        "employee_count":     request.form.get("employee_count", "50"),
        "remote_work_pct":    request.form.get("remote_work_pct", "0"),
        "cloud_heavy":        "cloud_heavy"       in request.form,
        "single_site":        "single_site"       in request.form,
        "has_ad":             "has_ad"             in request.form,
        "has_mfa":            "has_mfa"            in request.form,
        "has_edr":            "has_edr"            in request.form,
        "has_vuln_mgmt":      "has_vuln_mgmt"      in request.form,
        "has_email_security": "has_email_security" in request.form,
        "has_network_monitoring": "has_network_monitoring" in request.form,
        "has_sat":            "has_sat"             in request.form,
        "has_app_allowlisting": "has_app_allowlisting" in request.form,
        "has_backup":         "has_backup"          in request.form,
        "has_secure_config":  "has_secure_config"   in request.form,
        "has_dlp":            "has_dlp"             in request.form,
        "has_ir_plan":        "has_ir_plan"         in request.form,
        "has_asset_inventory":  "has_asset_inventory"  in request.form,
        "has_software_inventory": "has_software_inventory" in request.form,
        "needs_hipaa":        "needs_hipaa"         in request.form,
        "needs_soc2":         "needs_soc2"          in request.form,
    }

    # Coerce numeric fields before anonymization
    intake_raw["employee_count"]  = int(intake_raw["employee_count"])
    intake_raw["remote_work_pct"] = int(intake_raw["remote_work_pct"])

    # ── Anonymize ──────────────────────────────────────────────────────────────
    anon = Anonymizer(session_id=session_id)
    intake_clean = anon.anonymize(intake_raw)
    company_token = intake_clean.get("company_name", f"CLIENT_{session_id[:8].upper()}")

    # ── Score ──────────────────────────────────────────────────────────────────
    result = score_intake(intake_clean)

    # ── AI generation ──────────────────────────────────────────────────────────
    sys_p, user_p = risk_assessment_prompt(result.summary, result.control_gaps, intake_clean)
    ai_risk = query(sys_p, user_p)

    sys_p, user_p = pricing_justification_prompt(result, intake_clean)
    ai_pricing = query(sys_p, user_p)

    ai_compliance = None
    comp = compliance_gap_prompt(intake_clean, result.control_gaps)
    if comp[0]:
        ai_compliance = query(comp[0], comp[1])

    ai_insurance = None
    if result.tier.startswith("Tier 2"):
        sys_p, user_p = insurance_baseline_prompt(intake_clean, result.control_gaps, result.recommended_tools)
        ai_insurance = query(sys_p, user_p)

    # ── Generate PDF ───────────────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"assessment_{session_id[:8]}_{timestamp}.pdf"
    out_path  = os.path.join(REPORTS_DIR, filename)

    generate_report(
        output_path=out_path,
        company_token=company_token,
        scoring_result=result,
        ai_risk_text=ai_risk,
        ai_pricing_text=ai_pricing,
        ai_compliance_text=ai_compliance,
        ai_insurance_text=ai_insurance,
    )

    # ── Write cache for Discord bot /lastreport and /summary ──────────────────
    cache = {
        "client":        company_token,
        "score":         result.normalized_score,
        "tier":          result.tier,
        "upsell":        result.upsell,
        "price_low":     result.pricing_band["low"],
        "price_high":    result.pricing_band["high"],
        "price_period":  result.pricing_band["period"],
        "summary":       result.summary,
        "tools":         result.recommended_tools,
        "critical_gaps": [g["name"] for g in result.control_gaps if g["priority"] == "CRITICAL"],
        "all_gaps":      result.control_gaps,
        "filename":      filename,
        "timestamp":     datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    cache_path = os.path.join(os.path.dirname(REPORTS_DIR), "last_report.json")
    with open(cache_path, "w") as f:
        json.dump(cache, f, indent=2)

    return redirect(url_for("download_report", filename=filename))


@app.route("/report/<filename>")
def download_report(filename):
    filename = secure_filename(filename)
    path = os.path.join(REPORTS_DIR, filename)
    if not os.path.exists(path):
        flash("Report not found.")
        return redirect(url_for("index"))
    return send_file(path, as_attachment=True, download_name=filename)


if __name__ == "__main__":
    # Local only — never expose this to the internet
    app.run(host="127.0.0.1", port=5000, debug=False)
