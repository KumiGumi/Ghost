"""
ai/prompts.py

System and user prompts for each report module.
All prompts work with anonymized data only.
"""

SYSTEM_BASE = """You are a senior cybersecurity consultant writing professional security assessment reports for small and medium-sized businesses. Your writing is clear, direct, and jargon-free where possible. You use the CIS Controls framework (v8) as your baseline. You never invent findings — you only analyze what is explicitly provided. Format output as structured sections with headers. Be specific about remediation steps."""


def risk_assessment_prompt(scoring_summary: str, gaps: list[dict], intake: dict) -> tuple[str, str]:
    gap_text = "\n".join(
        f"- [{g['priority']}] {g['control']} — {g['name']}: {g['gap']} (Tool: {g.get('tool', 'TBD')})"
        for g in gaps
    )
    user_msg = f"""
Generate a risk assessment report section based on the following data.

CLIENT SUMMARY:
{scoring_summary}

CONTROL GAPS IDENTIFIED:
{gap_text}

ADDITIONAL CONTEXT:
- Compliance requirements: HIPAA={intake.get('needs_hipaa', False)}, SOC2={intake.get('needs_soc2', False)}
- Remote workforce: {intake.get('remote_work_pct', 0)}%
- Cloud-heavy environment: {intake.get('cloud_heavy', False)}
- Single site: {intake.get('single_site', True)}

Write the following sections:
1. Executive Summary (2-3 paragraphs, non-technical, suitable for a business owner)
2. Risk Findings (table format: Control | Gap | Risk Level | Recommended Action)
3. Remediation Roadmap (prioritized 30/60/90 day plan)
4. Compliance Posture (only if HIPAA or SOC2 is required)
"""
    return SYSTEM_BASE, user_msg


def pricing_justification_prompt(scoring_result, intake: dict) -> tuple[str, str]:
    system = SYSTEM_BASE + "\nWhen writing pricing justifications, be concise, value-focused, and frame cost against risk exposure — not against competitor pricing."
    user_msg = f"""
Write a brief pricing justification (3-4 paragraphs) for the following engagement.

ENGAGEMENT DETAILS:
- Recommended tier: {scoring_result.tier}
- Risk score: {scoring_result.normalized_score}/100
- Pricing band: ${scoring_result.pricing_band['low']:,}–${scoring_result.pricing_band['high']:,} {scoring_result.pricing_band['period']}
- Recommended tools: {', '.join(scoring_result.recommended_tools)}
- Number of critical/high gaps: {sum(1 for g in scoring_result.control_gaps if g['priority'] in ('CRITICAL', 'HIGH'))}
- Compliance needs: HIPAA={intake.get('needs_hipaa', False)}, SOC2={intake.get('needs_soc2', False)}

Frame the value in terms of:
1. What specific risks are being mitigated
2. What the cost of a breach or compliance failure would look like for a company this size
3. What is included at this price point
"""
    return system, user_msg


def compliance_gap_prompt(intake: dict, gaps: list[dict]) -> tuple[str, str]:
    frameworks = []
    if intake.get("needs_hipaa"):
        frameworks.append("HIPAA")
    if intake.get("needs_soc2"):
        frameworks.append("SOC 2 Type II")
    if not frameworks:
        return None, None  # Skip if no compliance requirements

    gap_text = "\n".join(f"- {g['control']}: {g['name']}" for g in gaps)
    user_msg = f"""
Generate a compliance gap analysis for the following frameworks: {', '.join(frameworks)}

CONTROL GAPS IDENTIFIED:
{gap_text}

For each applicable framework:
1. Map each gap to specific framework requirements (e.g., HIPAA §164.312, SOC2 CC6.x)
2. Assess the gap as: Compliant | Partial | Non-Compliant
3. Provide a specific remediation action
4. Flag any gaps that represent immediate audit risk

Format as a table per framework.
"""
    return SYSTEM_BASE, user_msg


def insurance_baseline_prompt(intake: dict, gaps: list[dict], tools: list[str]) -> tuple[str, str]:
    user_msg = f"""
Write a cyber insurance readiness summary for a small business client.

CURRENT POSTURE:
- Controls in place: {14 - len(gaps)} of {14} CIS IG1 controls
- Missing critical controls: {', '.join(g['name'] for g in gaps if g['priority'] == 'CRITICAL')}
- Recommended tools for compliance: {', '.join(tools)}

Write:
1. Insurance Readiness Summary — what they currently qualify for and what they don't
2. Minimum Required Controls — the 5-7 controls most insurers require before issuing a policy
3. Implementation Plan — what needs to happen before they apply, in order of importance
4. Ongoing Requirements — log review cadence and documentation insurers typically require for claims

Keep language accessible to a non-technical business owner.
"""
    return SYSTEM_BASE, user_msg
