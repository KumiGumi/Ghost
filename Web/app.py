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
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-change-this")

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "../data/reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


# ── HTML Templates ─────────────────────────────────────────────────────────────

FORM_HTML = r"""

<!DOCTYPE html>
<html>
<head>
    <title>Client Security Intake</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #0f1117; color: #e0e0e0; padding: 40px 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { color: #fff; font-size: 24px; margin-bottom: 6px; }
        .subtitle { color: #6c757d; font-size: 14px; margin-bottom: 32px; }
        .section { background: #1a1f2e; border-radius: 10px; padding: 24px;
                   margin-bottom: 16px; border: 1px solid #2d3561; }
        .section-header { display: flex; align-items: center; justify-content: space-between;
                          cursor: pointer; user-select: none; }
        .section-header h2 { color: #7c8cf8; font-size: 13px; text-transform: uppercase;
                              letter-spacing: 1px; }
        .cis-badge { background: #2d3561; color: #7c8cf8; font-size: 11px; font-weight: 700;
                     padding: 3px 8px; border-radius: 4px; }
        .section-body { margin-top: 16px; }
        .collapsible .section-body { display: none; }
        .collapsible.open .section-body { display: block; }
        .toggle-icon { color: #6c757d; font-size: 16px; transition: transform 0.2s; }
        .collapsible.open .toggle-icon { transform: rotate(180deg); }
        .field { margin-bottom: 14px; }
        label.field-label { display: block; font-size: 13px; color: #adb5bd; margin-bottom: 6px; }
        input[type=text], input[type=number], select {
            width: 100%; padding: 9px 12px; background: #0f1117;
            border: 1px solid #2d3561; border-radius: 6px; color: #e0e0e0; font-size: 13px; }
        input:focus, select:focus { outline: none; border-color: #7c8cf8; }
        .safeguard-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        .check-item { display: flex; align-items: flex-start; gap: 8px; font-size: 12px;
                      color: #c0c0c0; cursor: pointer; padding: 6px 8px;
                      border-radius: 5px; border: 1px solid transparent;
                      transition: border-color 0.15s, background 0.15s; }
        .check-item:hover { border-color: #2d3561; background: #0f1117; }
        .check-item input[type=checkbox] { width: 14px; height: 14px; margin-top: 2px;
                                           accent-color: #7c8cf8; flex-shrink: 0; }
        .check-item span { line-height: 1.4; }
        .hint { color: #6c757d; font-size: 11px; margin-bottom: 12px; font-style: italic; }
        .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        button[type=submit] {
            width: 100%; padding: 14px; background: #e63946; color: white;
            border: none; border-radius: 8px; font-size: 16px; font-weight: 600;
            cursor: pointer; margin-top: 8px; }
        button[type=submit]:hover { background: #c1121f; }
        .expand-all { background: none; border: 1px solid #2d3561; color: #7c8cf8;
                      font-size: 12px; padding: 6px 12px; border-radius: 5px;
                      cursor: pointer; margin-bottom: 16px; }
        .expand-all:hover { background: #1a1f2e; }
        .disclaimer { color: #6c757d; font-size: 11px; text-align: center; margin-top: 16px; }
        .progress-bar { background: #0f1117; border-radius: 4px; height: 4px;
                        margin-top: 10px; overflow: hidden; }
        .progress-fill { background: #7c8cf8; height: 100%; width: 0%;
                         transition: width 0.3s; border-radius: 4px; }
    </style>
</head>
<body>
<div class="container">
    <h1>Client Security Intake</h1>
    <p class="subtitle">CIS IG1 baseline assessment · Data anonymized before AI processing</p>

    <button type="button" class="expand-all" onclick="expandAll()">Expand All Sections</button>

    <div class="progress-bar"><div class="progress-fill" id="progress"></div></div>
    <p class="hint" style="text-align:right; margin-top:4px;" id="progress-label">0 safeguards checked</p>

    <form method="POST" action="/submit" id="intake-form">

        <!-- ── Organization ── -->
        <div class="section">
            <h2 class="section-header" style="cursor:default">Organization</h2>
            <div class="section-body" style="display:block">
                <div class="row2">
                    <div class="field">
                        <label class="field-label">Company Name</label>
                        <input type="text" name="company_name" placeholder="Acme Corp" required>
                    </div>
                    <div class="field">
                        <label class="field-label">Industry Vertical</label>
                        <select name="vertical">
                            <option value="healthcare">Healthcare</option>
                            <option value="finance">Finance / Banking</option>
                            <option value="legal">Legal</option>
                            <option value="technology">Technology</option>
                            <option value="retail">Retail</option>
                            <option value="education">Education</option>
                            <option value="manufacturing">Manufacturing</option>
                            <option value="nonprofit">Non-Profit</option>
                            <option value="government">Government</option>
                            <option value="other" selected>Other</option>
                        </select>
                    </div>
                </div>
                <div class="row2">
                    <div class="field">
                        <label class="field-label">Number of Employees</label>
                        <input type="number" name="employee_count" min="1" max="500" value="50" required>
                    </div>
                    <div class="field">
                        <label class="field-label">Remote Workforce %</label>
                        <input type="number" name="remote_work_pct" min="0" max="100" value="0">
                    </div>
                </div>
                <div class="safeguard-grid" style="margin-top:8px">
                    <label class="check-item"><input type="checkbox" name="cloud_heavy">
                        <span>Heavy cloud usage (M365 / Google / AWS)</span></label>
                    <label class="check-item"><input type="checkbox" name="single_site">
                        <span>Single physical location</span></label>
                    <label class="check-item"><input type="checkbox" name="needs_hipaa">
                        <span>HIPAA compliance required</span></label>
                    <label class="check-item"><input type="checkbox" name="needs_soc2">
                        <span>SOC 2 Type II required</span></label>
                </div>
            </div>
        </div>

        <!-- ── CIS 1 ── -->
        <div class="section collapsible" id="cis1">
            <div class="section-header" onclick="toggle('cis1')">
                <h2>Asset Inventory <span class="cis-badge">CIS 1</span></h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-body">
                <p class="hint">Does the organization know what hardware and systems it owns and operates?</p>
                <div class="safeguard-grid">
                    <label class="check-item"><input type="checkbox" name="asset_inventory_maintained" class="sf">
                        <span>Enterprise asset inventory is maintained (servers, workstations, network devices)</span></label>
                    <label class="check-item"><input type="checkbox" name="asset_inventory_reviewed" class="sf">
                        <span>Inventory is reviewed and updated at least quarterly</span></label>
                </div>
            </div>
        </div>

        <!-- ── CIS 2 ── -->
        <div class="section collapsible" id="cis2">
            <div class="section-header" onclick="toggle('cis2')">
                <h2>Software Inventory <span class="cis-badge">CIS 2</span></h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-body">
                <p class="hint">Does the organization track what software is authorized and installed?</p>
                <div class="safeguard-grid">
                    <label class="check-item"><input type="checkbox" name="software_inventory_maintained" class="sf">
                        <span>Authorized software list is maintained</span></label>
                    <label class="check-item"><input type="checkbox" name="unauthorized_software_blocked" class="sf">
                        <span>Unauthorized software is identified and removed promptly</span></label>
                </div>
            </div>
        </div>

        <!-- ── CIS 3 ── -->
        <div class="section collapsible" id="cis3">
            <div class="section-header" onclick="toggle('cis3')">
                <h2>Data Protection <span class="cis-badge">CIS 3</span></h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-body">
                <p class="hint">Is sensitive data identified, classified, and protected?</p>
                <div class="safeguard-grid">
                    <label class="check-item"><input type="checkbox" name="data_inventory_exists" class="sf">
                        <span>Sensitive data is identified and inventoried</span></label>
                    <label class="check-item"><input type="checkbox" name="data_encrypted_at_rest" class="sf">
                        <span>Sensitive data encrypted at rest (disk encryption, DB encryption)</span></label>
                    <label class="check-item"><input type="checkbox" name="data_encrypted_in_transit" class="sf">
                        <span>Data encrypted in transit (TLS/HTTPS enforced)</span></label>
                </div>
            </div>
        </div>

        <!-- ── CIS 4 ── -->
        <div class="section collapsible" id="cis4">
            <div class="section-header" onclick="toggle('cis4')">
                <h2>Secure Configuration <span class="cis-badge">CIS 4</span></h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-body">
                <p class="hint">Are devices and systems configured securely from the start?</p>
                <div class="safeguard-grid">
                    <label class="check-item"><input type="checkbox" name="secure_config_process" class="sf">
                        <span>Documented secure configuration standards exist for endpoints</span></label>
                    <label class="check-item"><input type="checkbox" name="default_passwords_changed" class="sf">
                        <span>Default passwords changed on all network devices and systems</span></label>
                    <label class="check-item"><input type="checkbox" name="auto_session_lock" class="sf">
                        <span>Automatic screen lock configured (15 min or less)</span></label>
                </div>
            </div>
        </div>

        <!-- ── CIS 5 ── -->
        <div class="section collapsible" id="cis5">
            <div class="section-header" onclick="toggle('cis5')">
                <h2>Account Management <span class="cis-badge">CIS 5</span></h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-body">
                <p class="hint">Are user accounts centrally managed and controlled?</p>
                <div class="safeguard-grid">
                    <label class="check-item"><input type="checkbox" name="centralized_identity" class="sf">
                        <span>Centralized identity management in place (Active Directory, Entra ID, Google Workspace)</span></label>
                    <label class="check-item"><input type="checkbox" name="dormant_accounts_disabled" class="sf">
                        <span>Dormant/unused accounts disabled within 30 days of inactivity</span></label>
                    <label class="check-item"><input type="checkbox" name="admin_accounts_inventoried" class="sf">
                        <span>Admin and privileged accounts are inventoried and reviewed</span></label>
                    <label class="check-item"><input type="checkbox" name="unique_passwords_enforced" class="sf">
                        <span>Unique passwords enforced — no shared or default account credentials</span></label>
                </div>
            </div>
        </div>

        <!-- ── CIS 6 ── -->
        <div class="section collapsible" id="cis6">
            <div class="section-header" onclick="toggle('cis6')">
                <h2>Access Control / MFA <span class="cis-badge">CIS 6</span></h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-body">
                <p class="hint">Is access to systems and data appropriately restricted and protected?</p>
                <div class="safeguard-grid">
                    <label class="check-item"><input type="checkbox" name="mfa_external_apps" class="sf">
                        <span>MFA enabled on all externally-accessible applications (email, portals)</span></label>
                    <label class="check-item"><input type="checkbox" name="mfa_remote_access" class="sf">
                        <span>MFA required for all remote/VPN access</span></label>
                    <label class="check-item"><input type="checkbox" name="mfa_admin_accounts" class="sf">
                        <span>MFA enforced on all admin and privileged accounts</span></label>
                    <label class="check-item"><input type="checkbox" name="least_privilege_enforced" class="sf">
                        <span>Least privilege principle applied — users have only necessary access</span></label>
                </div>
            </div>
        </div>

        <!-- ── CIS 7 ── -->
        <div class="section collapsible" id="cis7">
            <div class="section-header" onclick="toggle('cis7')">
                <h2>Vulnerability Management <span class="cis-badge">CIS 7</span></h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-body">
                <p class="hint">Does the organization actively find and fix vulnerabilities?</p>
                <div class="safeguard-grid">
                    <label class="check-item"><input type="checkbox" name="vuln_scanning_performed" class="sf">
                        <span>Automated vulnerability scanning is performed</span></label>
                    <label class="check-item"><input type="checkbox" name="vuln_scan_frequency" class="sf">
                        <span>Scans performed at least quarterly (monthly preferred)</span></label>
                    <label class="check-item"><input type="checkbox" name="patch_process_exists" class="sf">
                        <span>Documented patching process exists with assigned ownership</span></label>
                    <label class="check-item"><input type="checkbox" name="critical_patches_30days" class="sf">
                        <span>Critical/high vulnerabilities patched within 30 days</span></label>
                </div>
            </div>
        </div>

        <!-- ── CIS 8 ── -->
        <div class="section collapsible" id="cis8">
            <div class="section-header" onclick="toggle('cis8')">
                <h2>Audit Log Management <span class="cis-badge">CIS 8</span></h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-body">
                <p class="hint">Are system and security logs being collected, stored, and reviewed?</p>
                <div class="safeguard-grid">
                    <label class="check-item"><input type="checkbox" name="audit_logs_collected" class="sf">
                        <span>Audit logs collected from key systems (servers, firewalls, identity systems)</span></label>
                    <label class="check-item"><input type="checkbox" name="log_retention_90days" class="sf">
                        <span>Logs retained for minimum 90 days</span></label>
                    <label class="check-item"><input type="checkbox" name="logs_reviewed_regularly" class="sf">
                        <span>Logs reviewed on a defined schedule (weekly minimum)</span></label>
                </div>
            </div>
        </div>

        <!-- ── CIS 9 ── -->
        <div class="section collapsible" id="cis9">
            <div class="section-header" onclick="toggle('cis9')">
                <h2>Email & Web Protections <span class="cis-badge">CIS 9</span></h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-body">
                <p class="hint">Are email and web browsing protected against common attack vectors?</p>
                <div class="safeguard-grid">
                    <label class="check-item"><input type="checkbox" name="email_antimalware" class="sf">
                        <span>Email anti-malware and anti-phishing protection deployed</span></label>
                    <label class="check-item"><input type="checkbox" name="dns_filtering" class="sf">
                        <span>DNS filtering in place to block malicious domains</span></label>
                    <label class="check-item"><input type="checkbox" name="email_filtering_rules" class="sf">
                        <span>SPF, DKIM, and DMARC configured for email domains</span></label>
                    <label class="check-item"><input type="checkbox" name="malicious_attachment_blocking" class="sf">
                        <span>Malicious file type attachments blocked at email gateway</span></label>
                </div>
            </div>
        </div>

        <!-- ── CIS 10 ── -->
        <div class="section collapsible" id="cis10">
            <div class="section-header" onclick="toggle('cis10')">
                <h2>Malware Defenses / EDR <span class="cis-badge">CIS 10</span></h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-body">
                <p class="hint">Are endpoints protected against malware and malicious activity?</p>
                <div class="safeguard-grid">
                    <label class="check-item"><input type="checkbox" name="edr_deployed" class="sf">
                        <span>EDR / endpoint protection deployed on all managed endpoints</span></label>
                    <label class="check-item"><input type="checkbox" name="edr_signatures_autoupdate" class="sf">
                        <span>Anti-malware signatures configured to auto-update</span></label>
                    <label class="check-item"><input type="checkbox" name="edr_centrally_managed" class="sf">
                        <span>EDR centrally managed and actively monitored</span></label>
                    <label class="check-item"><input type="checkbox" name="removable_media_controlled" class="sf">
                        <span>Removable media use controlled / autorun disabled</span></label>
                </div>
            </div>
        </div>

        <!-- ── CIS 11 ── -->
        <div class="section collapsible" id="cis11">
            <div class="section-header" onclick="toggle('cis11')">
                <h2>Data Recovery & Backup <span class="cis-badge">CIS 11</span></h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-body">
                <p class="hint">Can the organization recover from a ransomware or data loss event?</p>
                <div class="safeguard-grid">
                    <label class="check-item"><input type="checkbox" name="backups_automated" class="sf">
                        <span>Automated backups configured for critical data and systems</span></label>
                    <label class="check-item"><input type="checkbox" name="backups_offsite_or_cloud" class="sf">
                        <span>Backups stored offsite or in a separate cloud environment</span></label>
                    <label class="check-item"><input type="checkbox" name="backup_restore_tested" class="sf">
                        <span>Backup restore tested successfully within the last 12 months</span></label>
                    <label class="check-item"><input type="checkbox" name="backups_encrypted" class="sf">
                        <span>Backup data is encrypted</span></label>
                </div>
            </div>
        </div>

        <!-- ── CIS 12 ── -->
        <div class="section collapsible" id="cis12">
            <div class="section-header" onclick="toggle('cis12')">
                <h2>Network Management <span class="cis-badge">CIS 12</span></h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-body">
                <p class="hint">Is the network infrastructure documented, patched, and segmented?</p>
                <div class="safeguard-grid">
                    <label class="check-item"><input type="checkbox" name="network_diagram_exists" class="sf">
                        <span>Network diagram / documentation exists and is current</span></label>
                    <label class="check-item"><input type="checkbox" name="network_devices_patched" class="sf">
                        <span>Firewalls and network devices on current firmware</span></label>
                    <label class="check-item"><input type="checkbox" name="guest_network_segmented" class="sf">
                        <span>Guest / untrusted devices on separate segmented network</span></label>
                </div>
            </div>
        </div>

        <!-- ── CIS 13 ── -->
        <div class="section collapsible" id="cis13">
            <div class="section-header" onclick="toggle('cis13')">
                <h2>Network Monitoring <span class="cis-badge">CIS 13</span></h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-body">
                <p class="hint">Is the network being monitored for threats and anomalies?</p>
                <div class="safeguard-grid">
                    <label class="check-item"><input type="checkbox" name="security_alerts_centralized" class="sf">
                        <span>Security event alerting centralized (SIEM or managed SOC)</span></label>
                    <label class="check-item"><input type="checkbox" name="intrusion_detection" class="sf">
                        <span>Intrusion detection / prevention deployed on network perimeter</span></label>
                </div>
            </div>
        </div>

        <!-- ── CIS 14 ── -->
        <div class="section collapsible" id="cis14">
            <div class="section-header" onclick="toggle('cis14')">
                <h2>Security Awareness Training <span class="cis-badge">CIS 14</span></h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-body">
                <p class="hint">Are employees trained to recognize and respond to security threats?</p>
                <div class="safeguard-grid">
                    <label class="check-item"><input type="checkbox" name="sat_program_exists" class="sf">
                        <span>Formal security awareness training program exists</span></label>
                    <label class="check-item"><input type="checkbox" name="sat_annual_training" class="sf">
                        <span>All staff complete security training at least annually</span></label>
                    <label class="check-item"><input type="checkbox" name="phishing_simulation_run" class="sf">
                        <span>Phishing simulations conducted at least twice per year</span></label>
                    <label class="check-item"><input type="checkbox" name="sat_covers_social_eng" class="sf">
                        <span>Training covers social engineering, BEC, and ransomware</span></label>
                </div>
            </div>
        </div>

        <!-- ── CIS 17 ── -->
        <div class="section collapsible" id="cis17">
            <div class="section-header" onclick="toggle('cis17')">
                <h2>Incident Response <span class="cis-badge">CIS 17</span></h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-body">
                <p class="hint">Does the organization have a plan to respond to a security incident?</p>
                <div class="safeguard-grid">
                    <label class="check-item"><input type="checkbox" name="ir_plan_documented" class="sf">
                        <span>Incident response plan is documented</span></label>
                    <label class="check-item"><input type="checkbox" name="ir_contacts_designated" class="sf">
                        <span>IR roles, contacts, and escalation paths designated</span></label>
                    <label class="check-item"><input type="checkbox" name="ir_plan_tested" class="sf">
                        <span>IR plan tested via tabletop exercise in last 12 months</span></label>
                    <label class="check-item"><input type="checkbox" name="ir_includes_ransomware" class="sf">
                        <span>IR plan specifically covers ransomware response</span></label>
                </div>
            </div>
        </div>

        <button type="submit">Generate Security Assessment Report</button>
    </form>
    <p class="disclaimer">Data anonymized before AI processing · Reports stored locally</p>
</div>

<script>
function toggle(id) {
    const el = document.getElementById(id);
    el.classList.toggle('open');
}
function expandAll() {
    document.querySelectorAll('.collapsible').forEach(el => el.classList.add('open'));
}
// Progress counter
document.querySelectorAll('.sf').forEach(cb => {
    cb.addEventListener('change', updateProgress);
});
function updateProgress() {
    const total = document.querySelectorAll('.sf').length;
    const checked = document.querySelectorAll('.sf:checked').length;
    const pct = Math.round(checked / total * 100);
    document.getElementById('progress').style.width = pct + '%';
    document.getElementById('progress-label').textContent =
        checked + ' of ' + total + ' safeguards confirmed';
}
</script>
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

    intake_raw = {
        "company_name":    request.form.get("company_name", "Client"),
        "vertical":        request.form.get("vertical", "other"),
        "employee_count":  request.form.get("employee_count", "50"),
        "remote_work_pct": request.form.get("remote_work_pct", "0"),
        "cloud_heavy":     "cloud_heavy" in request.form,
        "single_site":     "single_site" in request.form,
        "needs_hipaa":     "needs_hipaa" in request.form,
        "needs_soc2":      "needs_soc2"  in request.form,
        "asset_inventory_maintained": "asset_inventory_maintained" in request.form,
        "asset_inventory_reviewed": "asset_inventory_reviewed" in request.form,
        "software_inventory_maintained": "software_inventory_maintained" in request.form,
        "unauthorized_software_blocked": "unauthorized_software_blocked" in request.form,
        "data_inventory_exists": "data_inventory_exists" in request.form,
        "data_encrypted_at_rest": "data_encrypted_at_rest" in request.form,
        "data_encrypted_in_transit": "data_encrypted_in_transit" in request.form,
        "secure_config_process": "secure_config_process" in request.form,
        "default_passwords_changed": "default_passwords_changed" in request.form,
        "auto_session_lock": "auto_session_lock" in request.form,
        "centralized_identity": "centralized_identity" in request.form,
        "dormant_accounts_disabled": "dormant_accounts_disabled" in request.form,
        "admin_accounts_inventoried": "admin_accounts_inventoried" in request.form,
        "unique_passwords_enforced": "unique_passwords_enforced" in request.form,
        "mfa_external_apps": "mfa_external_apps" in request.form,
        "mfa_remote_access": "mfa_remote_access" in request.form,
        "mfa_admin_accounts": "mfa_admin_accounts" in request.form,
        "least_privilege_enforced": "least_privilege_enforced" in request.form,
        "vuln_scanning_performed": "vuln_scanning_performed" in request.form,
        "vuln_scan_frequency": "vuln_scan_frequency" in request.form,
        "patch_process_exists": "patch_process_exists" in request.form,
        "critical_patches_30days": "critical_patches_30days" in request.form,
        "audit_logs_collected": "audit_logs_collected" in request.form,
        "log_retention_90days": "log_retention_90days" in request.form,
        "logs_reviewed_regularly": "logs_reviewed_regularly" in request.form,
        "email_antimalware": "email_antimalware" in request.form,
        "dns_filtering": "dns_filtering" in request.form,
        "email_filtering_rules": "email_filtering_rules" in request.form,
        "malicious_attachment_blocking": "malicious_attachment_blocking" in request.form,
        "edr_deployed": "edr_deployed" in request.form,
        "edr_signatures_autoupdate": "edr_signatures_autoupdate" in request.form,
        "edr_centrally_managed": "edr_centrally_managed" in request.form,
        "removable_media_controlled": "removable_media_controlled" in request.form,
        "backups_automated": "backups_automated" in request.form,
        "backups_offsite_or_cloud": "backups_offsite_or_cloud" in request.form,
        "backup_restore_tested": "backup_restore_tested" in request.form,
        "backups_encrypted": "backups_encrypted" in request.form,
        "network_diagram_exists": "network_diagram_exists" in request.form,
        "network_devices_patched": "network_devices_patched" in request.form,
        "guest_network_segmented": "guest_network_segmented" in request.form,
        "security_alerts_centralized": "security_alerts_centralized" in request.form,
        "intrusion_detection": "intrusion_detection" in request.form,
        "sat_program_exists": "sat_program_exists" in request.form,
        "sat_annual_training": "sat_annual_training" in request.form,
        "phishing_simulation_run": "phishing_simulation_run" in request.form,
        "sat_covers_social_eng": "sat_covers_social_eng" in request.form,
        "ir_plan_documented": "ir_plan_documented" in request.form,
        "ir_contacts_designated": "ir_contacts_designated" in request.form,
        "ir_plan_tested": "ir_plan_tested" in request.form,
        "ir_includes_ransomware": "ir_includes_ransomware" in request.form,
    }

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

    # ── Write Discord bot cache ────────────────────────────────────────────────
    cache = {
        "client":        company_token,
        "grade":         result.letter_grade,
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
    path = os.path.join(REPORTS_DIR, filename)
    if not os.path.exists(path):
        flash("Report not found.")
        return redirect(url_for("index"))
    return send_file(path, as_attachment=True, download_name=filename)


if __name__ == "__main__":
    # Local only — never expose this to the internet
    app.run(host="127.0.0.1", port=5000, debug=False)
