"""
scoring/engine.py

Weighted risk scoring engine with per-safeguard partial credit.
Each CIS IG1 control is assessed via multiple sub-questions from the intake form.
Partial implementation reduces (but does not eliminate) the gap penalty.
"""

from dataclasses import dataclass


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ScoringResult:
    raw_score: float
    normalized_score: int           # 0–100 (risk score, higher = worse)
    letter_grade: str               # A–F derived from score
    tier: str
    upsell: bool
    recommended_tools: list[str]
    control_gaps: list[dict]        # full gaps for report
    control_scores: list[dict]      # per-control completion % for charts
    pricing_band: dict
    summary: str


# ── Vertical risk multipliers ─────────────────────────────────────────────────

VERTICAL_WEIGHTS = {
    "healthcare":    1.30,
    "finance":       1.25,
    "legal":         1.20,
    "government":    1.20,
    "education":     1.10,
    "retail":        1.05,
    "manufacturing": 1.00,
    "technology":    1.05,
    "nonprofit":     0.95,
    "other":         1.00,
}


# ── CIS IG1 Safeguard definitions ─────────────────────────────────────────────
# Each control has a weight and a list of (form_field, safeguard_description, sub_weight)
# sub_weight is relative importance within the control

CIS_IG1_SAFEGUARDS = [
    {
        "id": "CIS 1", "name": "Asset Inventory", "weight": 5,
        "tool": None, "ig_level": 1,
        "safeguards": [
            ("asset_inventory_maintained",   "Enterprise asset inventory maintained",        60),
            ("asset_inventory_reviewed",     "Inventory reviewed/updated regularly",         40),
        ]
    },
    {
        "id": "CIS 2", "name": "Software Inventory", "weight": 5,
        "tool": None, "ig_level": 1,
        "safeguards": [
            ("software_inventory_maintained","Authorized software list maintained",          60),
            ("unauthorized_software_blocked","Unauthorized software addressed promptly",     40),
        ]
    },
    {
        "id": "CIS 3", "name": "Data Protection", "weight": 6,
        "tool": None, "ig_level": 1,
        "safeguards": [
            ("data_inventory_exists",        "Sensitive data identified and inventoried",    30),
            ("data_encrypted_at_rest",       "Sensitive data encrypted at rest",             35),
            ("data_encrypted_in_transit",    "Data encrypted in transit (TLS/HTTPS)",        35),
        ]
    },
    {
        "id": "CIS 4", "name": "Secure Configuration", "weight": 6,
        "tool": None, "ig_level": 1,
        "safeguards": [
            ("secure_config_process",        "Secure config standards documented",           30),
            ("default_passwords_changed",    "Default passwords changed on all devices",     40),
            ("auto_session_lock",            "Automatic session locking configured",         30),
        ]
    },
    {
        "id": "CIS 5", "name": "Account Management", "weight": 8,
        "tool": "Active Directory / Entra ID", "ig_level": 1,
        "safeguards": [
            ("centralized_identity",         "Centralized identity management (AD/Entra)",   35),
            ("dormant_accounts_disabled",    "Dormant accounts disabled within 30 days",     25),
            ("admin_accounts_inventoried",   "Admin/privileged accounts inventoried",        20),
            ("unique_passwords_enforced",    "Unique passwords enforced (no shared accounts)",20),
        ]
    },
    {
        "id": "CIS 6", "name": "Access Control / MFA", "weight": 12,
        "tool": "Duo / Okta", "ig_level": 1,
        "safeguards": [
            ("mfa_external_apps",            "MFA on all externally-exposed apps",           35),
            ("mfa_remote_access",            "MFA required for remote/VPN access",           35),
            ("mfa_admin_accounts",           "MFA on all admin/privileged accounts",         20),
            ("least_privilege_enforced",     "Least privilege principle enforced",           10),
        ]
    },
    {
        "id": "CIS 7", "name": "Vulnerability Management", "weight": 9,
        "tool": "Qualys", "ig_level": 1,
        "safeguards": [
            ("vuln_scanning_performed",      "Automated vulnerability scanning performed",   35),
            ("vuln_scan_frequency",          "Scans performed at least quarterly",           25),
            ("patch_process_exists",         "Documented patching process exists",           20),
            ("critical_patches_30days",      "Critical patches applied within 30 days",      20),
        ]
    },
    {
        "id": "CIS 8", "name": "Audit Log Management", "weight": 6,
        "tool": None, "ig_level": 1,
        "safeguards": [
            ("audit_logs_collected",         "Audit logs collected from key systems",        50),
            ("log_retention_90days",         "Logs retained for minimum 90 days",            30),
            ("logs_reviewed_regularly",      "Logs reviewed on regular schedule",            20),
        ]
    },
    {
        "id": "CIS 9", "name": "Email & Web Protections", "weight": 9,
        "tool": "Ironscales", "ig_level": 1,
        "safeguards": [
            ("email_antimalware",            "Email anti-malware / anti-phish deployed",     40),
            ("dns_filtering",                "DNS filtering in place",                       25),
            ("email_filtering_rules",        "Email filtering rules configured (SPF/DKIM/DMARC)", 25),
            ("malicious_attachment_blocking","Malicious file type blocking enabled",         10),
        ]
    },
    {
        "id": "CIS 10", "name": "Malware Defenses (EDR)", "weight": 12,
        "tool": "Huntress", "ig_level": 1,
        "safeguards": [
            ("edr_deployed",                 "EDR deployed on all endpoints",                40),
            ("edr_signatures_autoupdate",    "Anti-malware signatures auto-update",          20),
            ("edr_centrally_managed",        "EDR centrally managed / monitored",            25),
            ("removable_media_controlled",   "Removable media/autorun controlled",           15),
        ]
    },
    {
        "id": "CIS 11", "name": "Data Recovery & Backup", "weight": 7,
        "tool": None, "ig_level": 1,
        "safeguards": [
            ("backups_automated",            "Automated backups configured",                 35),
            ("backups_offsite_or_cloud",     "Backups stored offsite or in cloud",           25),
            ("backup_restore_tested",        "Backup restore tested in last 12 months",      30),
            ("backups_encrypted",            "Backup data encrypted",                        10),
        ]
    },
    {
        "id": "CIS 12", "name": "Network Management", "weight": 5,
        "tool": "Todyl", "ig_level": 1,
        "safeguards": [
            ("network_diagram_exists",       "Network diagram/documentation exists",         40),
            ("network_devices_patched",      "Network devices on current firmware",          35),
            ("guest_network_segmented",      "Guest/untrusted network segmented",            25),
        ]
    },
    {
        "id": "CIS 13", "name": "Network Monitoring", "weight": 5,
        "tool": "Todyl (optional IG1)", "ig_level": 1,
        "safeguards": [
            ("security_alerts_centralized",  "Security event alerting centralized",          50),
            ("intrusion_detection",          "Intrusion detection/prevention deployed",      50),
        ]
    },
    {
        "id": "CIS 14", "name": "Security Awareness Training", "weight": 6,
        "tool": "Ironscales / Huntress SAT", "ig_level": 1,
        "safeguards": [
            ("sat_program_exists",           "Formal security awareness program exists",     30),
            ("sat_annual_training",          "All staff trained at least annually",          30),
            ("phishing_simulation_run",      "Phishing simulations conducted",               25),
            ("sat_covers_social_eng",        "Training covers social engineering/BEC",       15),
        ]
    },
    {
        "id": "CIS 17", "name": "Incident Response", "weight": 5,
        "tool": None, "ig_level": 1,
        "safeguards": [
            ("ir_plan_documented",           "Incident response plan documented",            35),
            ("ir_contacts_designated",       "IR roles and contacts designated",             30),
            ("ir_plan_tested",               "IR plan tested/tabletop exercised",            25),
            ("ir_includes_ransomware",       "IR plan covers ransomware scenario",           10),
        ]
    },
]

# All safeguard field names for reference
ALL_SAFEGUARD_FIELDS = [
    sf[0]
    for ctrl in CIS_IG1_SAFEGUARDS
    for sf in ctrl["safeguards"]
]

TIER1_THRESHOLD  = 60
UPSELL_THRESHOLD = 40


def _letter_grade(score: int) -> str:
    if score <= 20: return "A"
    if score <= 35: return "B"
    if score <= 50: return "C"
    if score <= 65: return "D"
    return "F"


def _calc_pricing(score: int, employee_count: int, tier: str) -> dict:
    if tier.startswith("Tier 1"):
        size_adj = min(employee_count / 200 * 20000, 25000)
        return {
            "low":    int(95000 + size_adj),
            "high":   int(115000 + size_adj),
            "currency": "USD", "period": "annual"
        }
    else:
        base = 1500
        complexity = (score / 100) * 2000
        size_adj   = min(employee_count / 200 * 1000, 1000)
        return {
            "low":    int(base + complexity * 0.8 + size_adj),
            "high":   int(base + complexity + size_adj),
            "currency": "USD", "period": "monthly"
        }


def score_intake(intake: dict) -> ScoringResult:
    ec    = int(intake.get("employee_count", 50))
    vert  = intake.get("vertical", "other").lower()
    vmult = VERTICAL_WEIGHTS.get(vert, 1.0)

    total_weight = sum(c["weight"] for c in CIS_IG1_SAFEGUARDS)
    gap_score    = 0.0
    control_gaps = []
    control_scores = []

    for ctrl in CIS_IG1_SAFEGUARDS:
        safeguards = ctrl["safeguards"]
        total_sub_weight = sum(sf[2] for sf in safeguards)

        # Calculate what % of this control is implemented
        implemented_weight = sum(
            sf[2] for sf in safeguards
            if intake.get(sf[0], False)
        )
        completion_pct = implemented_weight / total_sub_weight if total_sub_weight else 0

        control_scores.append({
            "id":         ctrl["id"],
            "name":       ctrl["name"],
            "completion": round(completion_pct * 100),
            "weight":     ctrl["weight"],
        })

        # Gap contribution: fully implemented = 0, fully missing = full weight
        gap_contribution = ctrl["weight"] * (1 - completion_pct)
        gap_score += gap_contribution

        # Determine priority and record gap if not fully implemented
        if completion_pct < 1.0:
            missing = [sf[1] for sf in safeguards if not intake.get(sf[0], False)]
            if completion_pct == 0:
                priority = "CRITICAL" if ctrl["weight"] >= 9 else "HIGH" if ctrl["weight"] >= 6 else "MEDIUM"
            elif completion_pct < 0.5:
                priority = "HIGH" if ctrl["weight"] >= 9 else "MEDIUM"
            else:
                priority = "MEDIUM" if ctrl["weight"] >= 9 else "LOW"

            control_gaps.append({
                "control":    ctrl["id"],
                "name":       ctrl["name"],
                "completion": round(completion_pct * 100),
                "priority":   priority,
                "tool":       ctrl.get("tool"),
                "missing":    missing,
            })

    # Compliance uplift
    compliance_score = 0
    if intake.get("needs_hipaa"):  compliance_score += 15
    if intake.get("needs_soc2"):   compliance_score += 12

    # Remote/cloud uplift
    remote_pct   = int(intake.get("remote_work_pct", 0))
    cloud_uplift = 8 if intake.get("cloud_heavy") else 0
    remote_uplift = int((remote_pct / 100) * 10)
    size_score    = min(ec / 200 * 10, 10)

    raw = (
        (gap_score / total_weight * 50)
        + compliance_score
        + cloud_uplift
        + remote_uplift
        + size_score
    ) * vmult

    normalized = min(int(raw), 100)
    grade  = _letter_grade(normalized)

    if normalized >= TIER1_THRESHOLD:
        tier, upsell = "Tier 1 - vCISO", False
    elif normalized >= UPSELL_THRESHOLD:
        tier, upsell = "Tier 2 - Insurance Baseline", True
    else:
        tier, upsell = "Tier 2 - Insurance Baseline", False

    # Tool recommendations
    tools = ["Huntress (EDR + Managed SOC)", "Ironscales (Email Security)"]
    if normalized >= 50 or intake.get("needs_hipaa") or intake.get("needs_soc2"):
        tools.append("Qualys (Vulnerability Management)")
    if not intake.get("mfa_external_apps") or not intake.get("mfa_remote_access"):
        tools.append("Duo / Okta (MFA)")
    if intake.get("single_site") and not intake.get("intrusion_detection"):
        tools.append("Todyl (Edge Security / UTM)")
    elif not intake.get("single_site"):
        tools.append("Todyl (SD-WAN / Network Defense)")
    tools = list(dict.fromkeys(tools))  # dedupe preserving order

    pricing = _calc_pricing(normalized, ec, tier)

    # Controls fully implemented (for summary)
    fully_implemented = [c for c in control_scores if c["completion"] == 100]
    critical_gaps = [g for g in control_gaps if g["priority"] == "CRITICAL"]

    summary = (
        f"Client is a {ec}-employee {vert} organization. "
        f"Risk score: {normalized}/100 (Grade {grade}). "
        f"CIS IG1 completion: {len(fully_implemented)}/{len(CIS_IG1_SAFEGUARDS)} controls fully implemented. "
        f"Critical gaps: {', '.join(g['name'] for g in critical_gaps) if critical_gaps else 'None'}. "
        f"Compliance: {'HIPAA ' if intake.get('needs_hipaa') else ''}{'SOC2' if intake.get('needs_soc2') else 'None specified'}. "
        f"Recommended tier: {tier}. "
        f"Estimated value: ${pricing['low']:,}–${pricing['high']:,} {pricing['period']}."
    )

    return ScoringResult(
        raw_score=raw,
        normalized_score=normalized,
        letter_grade=grade,
        tier=tier,
        upsell=upsell,
        recommended_tools=tools,
        control_gaps=control_gaps,
        control_scores=control_scores,
        pricing_band=pricing,
        summary=summary,
    )
