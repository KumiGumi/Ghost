"""
anonymizer/pipeline.py

Strips PII from client intake data before it touches the AI backend.
Stores a reversible token map in an encrypted local SQLite DB.
All data passed to AI uses tokens. De-anonymize after AI returns results.
"""

import re
import uuid
import json
import sqlite3
import os
from datetime import datetime
from cryptography.fernet import Fernet
from dotenv import load_dotenv

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_ROOT, ".env"))

DB_PATH = os.path.join(os.path.dirname(__file__), "../data/vault.db")
ENCRYPTION_KEY = os.getenv("VAULT_ENCRYPTION_KEY")


# ── Vault (encrypted SQLite token store) ─────────────────────────────────────

def _get_fernet():
    if not ENCRYPTION_KEY:
        raise ValueError("VAULT_ENCRYPTION_KEY not set in .env")
    return Fernet(ENCRYPTION_KEY.encode())


def _init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS token_vault (
            token TEXT PRIMARY KEY,
            encrypted_value BLOB NOT NULL,
            pii_type TEXT NOT NULL,
            client_session TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _store_token(token: str, real_value: str, pii_type: str, session_id: str):
    _init_db()
    f = _get_fernet()
    encrypted = f.encrypt(real_value.encode())
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO token_vault VALUES (?, ?, ?, ?, ?)",
        (token, encrypted, pii_type, session_id, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def _resolve_token(token: str) -> str | None:
    _init_db()
    f = _get_fernet()
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT encrypted_value FROM token_vault WHERE token = ?", (token,)
    ).fetchone()
    conn.close()
    if row:
        return f.decrypt(row[0]).decode()
    return None


# ── Anonymizer ────────────────────────────────────────────────────────────────

# Regex patterns for common PII
PII_PATTERNS = {
    "IP_ADDRESS":    r'\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b',
    "EMAIL":         r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b',
    "DOMAIN":        r'\b(?:[a-zA-Z0-9\-]+\.)+(?:com|net|org|io|co|us|gov|edu)\b',
    "PHONE":         r'\b(?:\+1[\s\-]?)?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}\b',
    "SSN":           r'\b\d{3}[\-\s]?\d{2}[\-\s]?\d{4}\b',
    "CREDIT_CARD":   r'\b(?:\d{4}[\s\-]?){3}\d{4}\b',
}


class Anonymizer:
    """
    Usage:
        anon = Anonymizer(session_id="client_abc_20240311")
        clean_data = anon.anonymize(raw_intake_dict)
        # ... send clean_data to AI ...
        real_data = anon.deanonymize(ai_output_text)
    """

    def __init__(self, session_id: str = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.local_map: dict[str, str] = {}  # token → original (in-memory cache)

    def _make_token(self, pii_type: str) -> str:
        short = str(uuid.uuid4())[:8].upper()
        return f"[{pii_type}_{short}]"

    def _replace(self, text: str, pattern: str, pii_type: str) -> str:
        def replace_match(m):
            original = m.group(0)
            # Reuse token if we've seen this exact value before
            existing = next(
                (t for t, v in self.local_map.items() if v == original), None
            )
            if existing:
                return existing
            token = self._make_token(pii_type)
            self.local_map[token] = original
            _store_token(token, original, pii_type, self.session_id)
            return token
        return re.sub(pattern, replace_match, text)

    def anonymize_text(self, text: str) -> str:
        """Strip PII from a single string."""
        for pii_type, pattern in PII_PATTERNS.items():
            text = self._replace(text, pattern, pii_type)
        return text

    def anonymize(self, data: dict) -> dict:
        """
        Recursively anonymize all string values in a dict.
        Leaves keys untouched (keys are field names, not PII).
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.anonymize_text(value)
            elif isinstance(value, dict):
                result[key] = self.anonymize(value)
            elif isinstance(value, list):
                result[key] = [
                    self.anonymize_text(v) if isinstance(v, str) else v
                    for v in value
                ]
            else:
                result[key] = value
        return result

    def deanonymize(self, text: str) -> str:
        """
        Replace all tokens in AI output with real values.
        Checks local in-memory map first, then vault.
        """
        for token in sorted(self.local_map.keys(), key=len, reverse=True):
            if token in text:
                text = text.replace(token, self.local_map[token])

        # Catch any tokens we don't have in memory (edge case)
        remaining = re.findall(r'\[[A-Z_]+_[A-F0-9]{8}\]', text)
        for token in remaining:
            real = _resolve_token(token)
            if real:
                text = text.replace(token, real)
        return text

    def get_session_tokens(self) -> list[dict]:
        """Return all tokens created in this session (for audit log)."""
        _init_db()
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT token, pii_type, created_at FROM token_vault WHERE client_session = ?",
            (self.session_id,)
        ).fetchall()
        conn.close()
        return [{"token": r[0], "type": r[1], "created": r[2]} for r in rows]


# ── Utility ───────────────────────────────────────────────────────────────────

def purge_session(session_id: str):
    """
    Hard-delete all tokens for a session.
    Use after report is finalized and delivered.
    """
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    deleted = conn.execute(
        "DELETE FROM token_vault WHERE client_session = ?", (session_id,)
    ).rowcount
    conn.commit()
    conn.close()
    return deleted
