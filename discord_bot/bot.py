"""
discord_bot/bot.py

Commands:
  /intake      — link to local web form
  /score       — quick risk score (full control set)
  /lastreport  — score + tier + pricing from last PDF run
  /summary     — micro report embed from last PDF run
  /reports     — list recent PDFs
  /status      — pipeline health check
"""

import os
import sys
import json
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

load_dotenv(os.path.join(_ROOT, ".env"))

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
REPORTS_DIR   = os.path.join(_ROOT, "data", "reports")
CACHE_FILE    = os.path.join(_ROOT, "data", "last_report.json")
WEB_URL       = "http://127.0.0.1:5000"

os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(os.path.join(_ROOT, "data"), exist_ok=True)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


# ── Events ─────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    from anonymizer.pipeline import _init_db
    _init_db()
    await tree.sync()
    print(f"Bot ready: {bot.user} | Slash commands synced")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _score_bar(score: int, width: int = 10) -> str:
    filled = round(score / 100 * width)
    return f"`{'█' * filled}{'░' * (width - filled)}` {score}/100"

def _score_color(score: int) -> int:
    if score >= 75: return 0xdc3545
    if score >= 55: return 0xfd7e14
    if score >= 35: return 0xffc107
    return 0x28a745

def _load_last_report() -> dict | None:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return json.load(f)
    return None

def _yes_no(val: str) -> bool:
    return val.strip().lower() in ("yes", "y", "true", "1")


# ── /intake ────────────────────────────────────────────────────────────────────

@tree.command(name="intake", description="Get the link to start a new client intake")
async def intake_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Client Intake Form",
        description=f"Open on your local machine:\n**{WEB_URL}**\n\nFill out the form to generate a full assessment PDF.",
        color=0xe63946,
    )
    embed.set_footer(text="Data is anonymized before AI processing. Local only.")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── /score ─────────────────────────────────────────────────────────────────────

@tree.command(name="score", description="Quick risk score for a client profile")
@app_commands.describe(
    employees="Number of employees",
    vertical="Industry: healthcare / finance / legal / technology / retail / manufacturing / nonprofit / other",
    has_ad="Centralized identity management (AD/Entra)? yes/no",
    has_mfa="MFA in place? yes/no",
    has_edr="EDR / endpoint protection? yes/no",
    has_email_security="Email security / anti-phish? yes/no",
    has_backup="Tested data backups? yes/no",
    has_ir_plan="Incident response plan? yes/no",
    needs_hipaa="HIPAA required? yes/no",
    needs_soc2="SOC 2 required? yes/no",
    remote_pct="Remote workforce percentage (0-100)",
)
async def score_cmd(
    interaction: discord.Interaction,
    employees: int,
    vertical: str = "other",
    has_ad: str = "no",
    has_mfa: str = "no",
    has_edr: str = "no",
    has_email_security: str = "no",
    has_backup: str = "no",
    has_ir_plan: str = "no",
    needs_hipaa: str = "no",
    needs_soc2: str = "no",
    remote_pct: int = 0,
):
    from scoring.engine import score_intake

    intake = {
        "employee_count":         employees,
        "vertical":               vertical.lower(),
        "remote_work_pct":        remote_pct,
        "cloud_heavy":            remote_pct > 30,
        "single_site":            True,
        "has_ad":                 _yes_no(has_ad),
        "has_mfa":                _yes_no(has_mfa),
        "has_edr":                _yes_no(has_edr),
        "has_vuln_mgmt":          False,
        "has_email_security":     _yes_no(has_email_security),
        "has_network_monitoring": False,
        "has_sat":                False,
        "has_app_allowlisting":   False,
        "has_backup":             _yes_no(has_backup),
        "has_secure_config":      False,
        "has_dlp":                False,
        "has_ir_plan":            _yes_no(has_ir_plan),
        "has_asset_inventory":    False,
        "has_software_inventory": False,
        "needs_hipaa":            _yes_no(needs_hipaa),
        "needs_soc2":             _yes_no(needs_soc2),
    }

    result = score_intake(intake)

    embed = discord.Embed(title="Quick Risk Score", color=_score_color(result.normalized_score))
    embed.add_field(name="Risk Score", value=_score_bar(result.normalized_score), inline=False)
    embed.add_field(name="Tier",       value=result.tier, inline=True)
    embed.add_field(name="Pricing",
                    value=f"${result.pricing_band['low']:,}–${result.pricing_band['high']:,} / {result.pricing_band['period']}",
                    inline=True)

    critical = [g for g in result.control_gaps if g["priority"] == "CRITICAL"]
    high     = [g for g in result.control_gaps if g["priority"] == "HIGH"]

    if critical:
        embed.add_field(
            name=f"🔴 Critical Gaps ({len(critical)})",
            value="\n".join(f"• {g['name']}" for g in critical),
            inline=False,
        )
    if high:
        embed.add_field(
            name=f"🟠 High Gaps ({len(high)})",
            value="\n".join(f"• {g['name']}" for g in high[:4]),
            inline=False,
        )

    embed.add_field(
        name="Recommended Tools",
        value="\n".join(f"• {t}" for t in result.recommended_tools),
        inline=False,
    )

    footer = "⚡ Strong Tier 1 upsell opportunity" if result.upsell else f"Total gaps: {len(result.control_gaps)}"
    embed.set_footer(text=footer)
    await interaction.response.send_message(embed=embed)


# ── /lastreport ────────────────────────────────────────────────────────────────

@tree.command(name="lastreport", description="Score and pricing from the last generated report")
async def lastreport_cmd(interaction: discord.Interaction):
    data = _load_last_report()
    if not data:
        await interaction.response.send_message(
            "No reports generated yet. Run an intake first.", ephemeral=True
        )
        return

    score = data.get("score", 0)
    embed = discord.Embed(
        title=f"Last Report — {data.get('client', 'Unknown')}",
        color=_score_color(score),
    )
    embed.add_field(name="Risk Score", value=_score_bar(score), inline=False)
    embed.add_field(name="Grade",      value=f"**{data.get("grade", "?")}**", inline=True)
    embed.add_field(name="Tier",       value=data.get("tier", "—"), inline=True)
    embed.add_field(name="Pricing",
                    value=f"${data.get('price_low', 0):,}–${data.get('price_high', 0):,} / {data.get('price_period', '—')}",
                    inline=True)
    embed.add_field(name="Generated",  value=data.get("timestamp", "—"), inline=True)
    embed.add_field(name="File",       value=f"`{data.get('filename', '—')}`", inline=False)

    critical = data.get("critical_gaps", [])
    if critical:
        embed.add_field(
            name=f"🔴 Critical Gaps ({len(critical)})",
            value="\n".join(f"• {g}" for g in critical),
            inline=False,
        )

    if data.get("upsell"):
        embed.set_footer(text="⚡ Upsell opportunity flagged for this client")

    await interaction.response.send_message(embed=embed)


# ── /summary ───────────────────────────────────────────────────────────────────

@tree.command(name="summary", description="Micro report summary from the last intake run")
async def summary_cmd(interaction: discord.Interaction):
    data = _load_last_report()
    if not data:
        await interaction.response.send_message(
            "No reports generated yet. Run an intake first.", ephemeral=True
        )
        return

    score = data.get("score", 0)
    embed = discord.Embed(
        title=f"Assessment Summary — {data.get('client', 'Unknown')}",
        description=data.get("summary", "No summary available."),
        color=_score_color(score),
    )

    gaps_by_priority = {}
    for g in data.get("all_gaps", []):
        p = g.get("priority", "LOW")
        gaps_by_priority.setdefault(p, []).append(g.get("name", ""))

    gap_lines = []
    for priority, icon in [("CRITICAL", "🔴"), ("HIGH", "🟠"), ("MEDIUM", "🟡")]:
        items = gaps_by_priority.get(priority, [])
        if items:
            gap_lines.append(f"{icon} **{priority}**: {', '.join(items)}")

    if gap_lines:
        embed.add_field(name="Control Gaps", value="\n".join(gap_lines), inline=False)

    embed.add_field(
        name="Recommended Stack",
        value="\n".join(f"• {t}" for t in data.get("tools", [])),
        inline=False,
    )
    embed.add_field(name="Tier",    value=data.get("tier", "—"), inline=True)
    embed.add_field(name="Score",   value=f"{score}/100", inline=True)
    embed.add_field(name="Pricing",
                    value=f"${data.get('price_low', 0):,}–${data.get('price_high', 0):,} / {data.get('price_period', '—')}",
                    inline=True)

    embed.set_footer(text=f"Generated: {data.get('timestamp', '—')} | Full PDF in data/reports/")
    await interaction.response.send_message(embed=embed)


# ── /reports ───────────────────────────────────────────────────────────────────

@tree.command(name="reports", description="List recently generated assessment reports")
async def reports_cmd(interaction: discord.Interaction):
    files = sorted(
        [f for f in os.listdir(REPORTS_DIR) if f.endswith(".pdf")],
        reverse=True
    )[:10]

    if not files:
        await interaction.response.send_message("No reports generated yet.", ephemeral=True)
        return

    embed = discord.Embed(title="Recent Assessment Reports", color=0x2d3561)
    for f in files:
        parts = f.replace(".pdf", "").split("_")
        date = parts[-2] if len(parts) >= 2 else "—"
        embed.add_field(name=f"`{f}`", value=f"Date: {date}", inline=False)

    embed.set_footer(text=f"Stored at: {REPORTS_DIR}")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── /status ────────────────────────────────────────────────────────────────────

@tree.command(name="status", description="Check pipeline health")
async def status_cmd(interaction: discord.Interaction):
    from ai.backend import BACKEND, OLLAMA_URL, OLLAMA_MODEL, ANTHROPIC_KEY

    vault_path = os.path.join(_ROOT, "data", "vault.db")

    checks = {
        "AI Backend":    f"`{BACKEND}`",
        "Anthropic Key": "✅ Set" if ANTHROPIC_KEY else "❌ Missing",
        "Reports Dir":   "✅ Ready" if os.path.isdir(REPORTS_DIR) else "❌ Missing",
        "Vault DB":      "✅ Ready" if os.path.exists(vault_path) else "❌ Missing",
        "Last Report":   "✅ Exists" if os.path.exists(CACHE_FILE) else "⚠️ None yet",
        "Web App":       f"Run `python Web/app.py` → `{WEB_URL}`",
    }

    if BACKEND == "ollama":
        checks["Ollama URL"]   = f"`{OLLAMA_URL}`"
        checks["Ollama Model"] = f"`{OLLAMA_MODEL}`"

    embed = discord.Embed(title="Pipeline Status", color=0x7c8cf8)
    for k, v in checks.items():
        embed.add_field(name=k, value=v, inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN not set in .env")
        sys.exit(1)
    bot.run(DISCORD_TOKEN)
