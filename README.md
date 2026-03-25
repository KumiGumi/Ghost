# MSSP Platform

Lightweight AI-augmented MSSP toolset.  
CIS IG1 baseline · Two-tier service model · Local-first · API-swappable AI

---

## Architecture

```
web/app.py          ← Intake form + pipeline orchestration (Flask)
anonymizer/         ← PII stripping + encrypted token vault (SQLite)
scoring/engine.py   ← Weighted risk score → tier + tool recommendations
ai/backend.py       ← Anthropic API or Ollama (swap via .env)
ai/prompts.py       ← Report section prompts
reports/generator.py← PDF generation (ReportLab)
discord_bot/bot.py  ← Slash commands (/intake /score /reports /status)
data/               ← vault.db + generated PDFs (gitignored)
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:
- `ANTHROPIC_API_KEY` — your Anthropic key
- `FLASK_SECRET_KEY` — any random string
- `VAULT_ENCRYPTION_KEY` — generate with:
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- `DISCORD_BOT_TOKEN` — from Discord Developer Portal

### 3. Run the web app

```bash
cd web
python app.py
```

Opens at http://127.0.0.1:5000 — **local only, do not expose externally**

### 4. Run the Discord bot (separate terminal)

```bash
cd discord_bot
python bot.py
```

---

## Discord Bot Setup

1. Go to https://discord.com/developers/applications
2. Create a new application → Bot → copy token → paste in `.env`
3. Enable: `applications.commands` scope + `bot` scope
4. Permissions: Send Messages, Embed Links, Use Slash Commands
5. Invite bot to your private server

### Slash Commands

| Command | Description |
|---------|-------------|
| `/intake` | Get link to intake form |
| `/score employees vertical has_mfa has_edr needs_hipaa` | Quick risk score |
| `/reports` | List recent PDFs |
| `/status` | Pipeline health check |

---

## Switching to Ollama (local AI)

```bash
# In .env:
AI_BACKEND=ollama
OLLAMA_MODEL=llama3.2

# Pull model
ollama pull llama3.2

# Run Ollama
ollama serve
```

No other code changes needed.

---

## Two-Tier Service Model

| | Tier 1 — vCISO | Tier 2 — Insurance Baseline |
|--|--|--|
| **Price** | ~$100k–$125k/yr | $1,500–$4,500/mo |
| **Meetings** | 4 quarterly + 1 annual strategy | As needed |
| **Log Reviews** | Weekly | If required by insurer |
| **Framework** | CIS IG1 + selective IG2 | Minimum viable |
| **Risk Score** | 65+ | <65 |

---

## Security Notes

- The web app binds to `127.0.0.1` only — never expose to LAN/internet
- Vault DB (`data/vault.db`) is encrypted with Fernet symmetric encryption
- API key lives in `.env`, never in code
- `data/` directory should be in `.gitignore`
- Run `purge_session(session_id)` after delivering each report to clean tokens

---

## Roadmap

- [ ] Log review scheduling + reminders (Discord)
- [ ] Quarterly report templates (separate from intake)
- [ ] Vendor risk flag feed (auto-update notes like Okta incident)
- [ ] Client portal (read-only report view per client)
- [ ] Ollama model benchmarking vs Anthropic for report quality
