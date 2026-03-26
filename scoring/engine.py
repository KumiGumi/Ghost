"""
scoring/engine.py

Weighted risk scoring engine.
Inputs: anonymized intake survey dict
Outputs: score (0-100), tier recommendation, tool triggers, gap list
"""

from dataclasses import dataclass, field


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ScoringResult:
    raw_score: float
    normalized_score: int          # 0–100
    tier: str                      # "Tier 1 - vCISO" | "Tier 2 - Insurance Baseline"
    upsell: bool                   # Tier 2 but close to Tier 1
    recommended_tools: list[str]
    control_gaps: list[dict]       # [{"control": "CIS 6", "gap": "No MFA", "priority": "HIGH"}]
    pricing_band: dict             # {"low": int, "high": int, "currency": "USD"}
    summary: str                   # one-paragraph plain-English summary for AI prompt context


# ── Vertical risk multipliers ─────────────────────────────────────────────────

VERTICAL_WEIGHTS = {
    "healthcare":       1.30,
    "finance":          1.25,
    "legal":            1.20,
    "government":       1.20,
    "education":        1.10,
    "retail":           1.05,
    "manufacturing":    1.00,
    "technology":       1.05,
    "nonprofit":        0.95,
    "other":            1.00,
}

# ── CIS IG1 controls checklist ────────────────────────────────────────────────
# Each control has a weight (impact on score if missing) and a priority tier

CIS_IG1_CONTROLS = [
    # id, name, weight, maps_to_tool
    ("C5-C6",  "Centralized Account/Access Management",  12, "Active Directory / Entra ID"),
    ("C6",     "Multi-Factor Authentication",            12, "Duo / Okta"),
    ("C10",    "Malware Defenses (EDR)",                 12, "Huntress"),
    ("C7",     "Vulnerability Management",                8, "Qualys"),
    ("C9",     "Email Security / Anti-Phishing",          8, "Ironscales"),
    ("C13",    "Network Monitoring / Defense",            6, "Todyl (optional IG1)"),
    ("C14",    "Security Awareness Training",             6, "Ironscales / Huntress SAT"),
    ("C16",    "Application Allow-Listing",               4, "AppLocker"),
    ("C11",    "Data Recovery / Backup",                  6, None),
    ("C4",     "Secure Config of Assets",                 5, None),
    ("C3",     "Data Protection (basic DLP)",             5, None),
    ("C17",    "Incident Response Plan",                  4, None),
    ("C1",     "Asset Inventory",                         4, None),
    ("C2",     "Software Inventory",                      4, None),
]

# ── Tier thresholds ───────────────────────────────────────────────────────────

TIER1_THRESHOLD  = 65   # vCISO
UPSELL_THRESHOLD = 45   # Tier 2 but pitch Tier 1


# ── Pricing bands ─────────────────────────────────────────────────────────────

def _calc_pricing(score: int, employee_count: int, vertical: str, tier: str) -> dict:
    """
    Rough pricing bands. Tier 1 anchors at $100k/yr.
    Tier 2 is monthly retainer based on complexity.
    """
    if tier.startswith("Tier 1"):
        # vCISO: flat $100k with small adjustment for size/complexity
        size_adj = min(employee_count / 200 * 20000, 25000)
        low  = int(95000 + size_adj)
        high = int(115000 + size_adj)
        return {"low": low, "high": high, "currency": "USD", "period": "annual"}
    else:
        # Tier 2: monthly retainer $1,500–$4,500/mo
        base = 1500
        complexity = (score / 100) * 2000
        size_adj   = min(employee_count / 200 * 1000, 1000)
        monthly_low  = int(base + complexity * 0.8 + size_adj)
        monthly_high = int(base + complexity + size_adj)
        return {
            "low":      monthly_low,
            "high":     monthly_high,
            "currency": "USD",
            "period":   "monthly"
        }


# ── Main scoring function ─────────────────────────────────────────────────────

def score_intake(intake: dict) -> ScoringResult:
    """
    intake dict keys (all from web form, already anonymized):
        employee_count: int
        vertical: str
        has_ad: bool
        has_mfa: bool
        has_edr: bool
        has_vuln_mgmt: bool
        has_email_security: bool
        has_network_monitoring: bool
        has_sat: bool           # security awareness training
        has_app_allowlisting: bool
        has_backup: bool
        has_secure_config: bool
        has_dlp: bool
        has_ir_plan: bool
        has_asset_inventory: bool
        has_software_inventory: bool
        needs_hipaa: bool
        needs_soc2: bool
        remote_work_pct: int    # 0–100
        cloud_heavy: bool
        single_site: bool
        # Security Maturity fields
        patch_cadence: str      # "within_7_days" | "within_30_days" | "irregular" | "none"
        has_priv_separation: bool
        has_password_policy: bool
        has_usb_control: bool
        has_firewall: bool
        backup_tested: bool
        has_siem: bool
        has_vendor_mgmt: bool
    """

    ec      = int(intake.get("employee_count", 50))
    vert    = intake.get("vertical", "other").lower()
    vmult   = VERTICAL_WEIGHTS.get(vert, 1.0)

    # ── Map controls to intake fields ────────────────────────────────────────
    control_map = {
        "C5-C6": intake.get("has_ad", False),
        "C6":    intake.get("has_mfa", False),
        "C10":   intake.get("has_edr", False),
        "C7":    intake.get("has_vuln_mgmt", False),
        "C9":    intake.get("has_email_security", False),
        "C13":   intake.get("has_network_monitoring", False),
        "C14":   intake.get("has_sat", False),
        "C16":   intake.get("has_app_allowlisting", False),
        "C11":   intake.get("has_backup", False),
        "C4":    intake.get("has_secure_config", False),
        "C3":    intake.get("has_dlp", False),
        "C17":   intake.get("has_ir_plan", False),
        "C1":    intake.get("has_asset_inventory", False),
        "C2":    intake.get("has_software_inventory", False),
    }

    # ── Gap scoring ───────────────────────────────────────────────────────────
    total_weight = sum(w for _, _, w, _ in CIS_IG1_CONTROLS)
    # Add weights for the new maturity controls
    total_weight += 6 + 5 + 5 + 3 + 6 + 4 + 5 + 4   # patch_cadence + 7 boolean controls
    gap_score    = 0.0
    gaps         = []

    for ctrl_id, ctrl_name, weight, tool in CIS_IG1_CONTROLS:
        has_control = control_map.get(ctrl_id, False)
        if not has_control:
            gap_score += weight
            priority = "CRITICAL" if weight >= 10 else "HIGH" if weight >= 6 else "MEDIUM"
            gaps.append({
                "control":  ctrl_id,
                "name":     ctrl_name,
                "gap":      f"Missing: {ctrl_name}",
                "priority": priority,
                "tool":     tool,
            })

    # ── Security Maturity gap scoring ─────────────────────────────────────────
    # patch_cadence: CIS C7 sub — weight 6
    patch_cadence = intake.get("patch_cadence", "none")
    if patch_cadence == "within_7_days":
        pass  # no gap
    elif patch_cadence == "within_30_days":
        gap_score += 3  # partial gap
        gaps.append({
            "control":  "C7",
            "name":     "Patch Management Cadence (30-day)",
            "gap":      "Patches applied within 30 days — consider accelerating to 7-day cycle",
            "priority": "MEDIUM",
            "tool":     "Qualys",
        })
    else:  # irregular or none
        gap_score += 6
        gaps.append({
            "control":  "C7",
            "name":     "Patch Management Cadence",
            "gap":      "Irregular or no patch management cadence",
            "priority": "HIGH",
            "tool":     "Qualys",
        })

    # has_priv_separation: CIS C5 — weight 5, priority MEDIUM
    if not intake.get("has_priv_separation", False):
        gap_score += 5
        gaps.append({
            "control":  "C5",
            "name":     "Privileged Account Separation",
            "gap":      "Admin/privileged accounts not separated from daily-use accounts",
            "priority": "MEDIUM",
            "tool":     "Active Directory / Entra ID",
        })

    # has_password_policy: CIS C5 — weight 5, priority MEDIUM
    if not intake.get("has_password_policy", False):
        gap_score += 5
        gaps.append({
            "control":  "C5",
            "name":     "Password Policy Enforcement",
            "gap":      "No enforced password policy (length, complexity, expiry)",
            "priority": "MEDIUM",
            "tool":     "Active Directory / Entra ID",
        })

    # has_usb_control: CIS C10 sub — weight 3, priority MEDIUM
    if not intake.get("has_usb_control", False):
        gap_score += 3
        gaps.append({
            "control":  "C10",
            "name":     "USB / Removable Media Control",
            "gap":      "USB/removable media not blocked or controlled",
            "priority": "MEDIUM",
            "tool":     "AppLocker / Endpoint DLP",
        })

    # has_firewall: CIS C13 — weight 6, priority HIGH
    if not intake.get("has_firewall", False):
        gap_score += 6
        gaps.append({
            "control":  "C13",
            "name":     "Firewall / Perimeter Defense",
            "gap":      "No firewall or perimeter security device in place",
            "priority": "HIGH",
            "tool":     "Todyl (Edge Security / UTM)",
        })

    # backup_tested: CIS C11 sub — weight 4, priority HIGH
    if not intake.get("backup_tested", False):
        gap_score += 4
        gaps.append({
            "control":  "C11",
            "name":     "Backup Testing",
            "gap":      "Backups not tested in the last 12 months",
            "priority": "HIGH",
            "tool":     None,
        })

    # has_siem: CIS C8 — weight 5, priority MEDIUM
    if not intake.get("has_siem", False):
        gap_score += 5
        gaps.append({
            "control":  "C8",
            "name":     "Logging / SIEM",
            "gap":      "No centralized logging or SIEM solution in place",
            "priority": "MEDIUM",
            "tool":     "Huntress (Managed SOC)",
        })

    # has_vendor_mgmt: CIS C15 — weight 4, priority MEDIUM
    if not intake.get("has_vendor_mgmt", False):
        gap_score += 4
        gaps.append({
            "control":  "C15",
            "name":     "Vendor / Third-Party Access Management",
            "gap":      "Vendor and third-party access not formally controlled",
            "priority": "MEDIUM",
            "tool":     None,
        })

    # ── Compliance uplift ─────────────────────────────────────────────────────
    compliance_score = 0
    if intake.get("needs_hipaa"):
        compliance_score += 15
    if intake.get("needs_soc2"):
        compliance_score += 12

    # ── Remote/cloud uplift ───────────────────────────────────────────────────
    remote_pct    = int(intake.get("remote_work_pct", 0))
    cloud_uplift  = 8 if intake.get("cloud_heavy") else 0
    remote_uplift = int((remote_pct / 100) * 10)

    # ── Employee size factor ──────────────────────────────────────────────────
    size_score = min(ec / 200 * 10, 10)

    # ── Combine ───────────────────────────────────────────────────────────────
    raw = (
        (gap_score / total_weight * 50)   # CIS gaps → up to 50 pts
        + compliance_score                 # compliance exposure
        + cloud_uplift
        + remote_uplift
        + size_score
    ) * vmult

    normalized = min(int(raw), 100)

    # ── Tier + upsell ─────────────────────────────────────────────────────────
    if normalized >= TIER1_THRESHOLD:
        tier   = "Tier 1 - vCISO"
        upsell = False
    elif normalized >= UPSELL_THRESHOLD:
        tier   = "Tier 2 - Insurance Baseline"
        upsell = True
    else:
        tier   = "Tier 2 - Insurance Baseline"
        upsell = False

    # ── Tool recommendations ──────────────────────────────────────────────────
    tools = ["Huntress (EDR + Managed SOC)", "Ironscales (Email Security)"]

    if normalized >= 50 or intake.get("needs_hipaa") or intake.get("needs_soc2"):
        tools.append("Qualys (Vulnerability Management)")

    if not intake.get("has_mfa"):
        tools.append("Duo / Okta (MFA)")

    if (intake.get("cloud_heavy") or remote_pct > 30 or not intake.get("has_mfa")) and "Duo / Okta (MFA)" not in tools:
        tools.append("Duo / Okta (MFA)")

    if intake.get("single_site") and not intake.get("has_network_monitoring"):
        tools.append("Todyl (Edge Security / UTM)")
    elif not intake.get("single_site") and normalized >= 55:
        tools.append("Todyl (SD-WAN / Network Defense)")

    # ── Pricing ───────────────────────────────────────────────────────────────
    pricing = _calc_pricing(normalized, ec, vert, tier)

    # ── Summary for AI prompt context ─────────────────────────────────────────
    gap_names = [g["name"] for g in gaps if g["priority"] in ("CRITICAL", "HIGH")]
    patch_note = ""
    if patch_cadence in ("irregular", "none"):
        patch_note = " Patch management cadence is a critical gap (irregular/none)."
    elif patch_cadence == "within_30_days":
        patch_note = " Patch management cadence is suboptimal (30-day cycle)."
    summary = (
        f"Client is a {ec}-employee {vert} organization with a risk score of {normalized}/100. "
        f"Recommended tier: {tier}. "
        f"Top control gaps: {', '.join(gap_names[:4]) if gap_names else 'None identified'}. "
        f"Compliance requirements: {'HIPAA ' if intake.get('needs_hipaa') else ''}"
        f"{'SOC2' if intake.get('needs_soc2') else ''}. "
        f"Estimated engagement value: ${pricing['low']:,}–${pricing['high']:,} {pricing['period']}."
        f"{patch_note}"
    )

    return ScoringResult(
        raw_score=raw,
        normalized_score=normalized,
        tier=tier,
        upsell=upsell,
        recommended_tools=tools,
        control_gaps=gaps,
        pricing_band=pricing,
        summary=summary,
    )
