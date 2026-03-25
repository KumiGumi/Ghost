"""
ai/backend.py

Abstraction layer over Anthropic API and Ollama.
Set AI_BACKEND=anthropic or AI_BACKEND=ollama in .env.
All other modules call query() and never touch the AI provider directly.
"""

import os
import json
import urllib.request
import urllib.error
from dotenv import load_dotenv

# Load .env from project root regardless of working directory
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_ROOT, ".env"))

BACKEND      = os.getenv("AI_BACKEND", "anthropic")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
OLLAMA_URL   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


def query(system_prompt: str, user_message: str, max_tokens: int = 2000) -> str:
    """
    Send a prompt to the configured AI backend.
    Returns the assistant's text response.
    """
    if BACKEND == "ollama":
        return _query_ollama(system_prompt, user_message, max_tokens)
    else:
        return _query_anthropic(system_prompt, user_message, max_tokens)


# ── Anthropic ─────────────────────────────────────────────────────────────────

def _query_anthropic(system_prompt: str, user_message: str, max_tokens: int) -> str:
    if not ANTHROPIC_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set in .env")

    payload = json.dumps({
        "model": "claude-sonnet-4-5",
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            return data["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"Anthropic API error {e.code}: {body}") from e


# ── Ollama ────────────────────────────────────────────────────────────────────

def _query_ollama(system_prompt: str, user_message: str, max_tokens: int) -> str:
    payload = json.dumps({
        "model":  OLLAMA_MODEL,
        "prompt": f"<system>\n{system_prompt}\n</system>\n\nUser: {user_message}",
        "stream": False,
        "options": {"num_predict": max_tokens},
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            return data.get("response", "")
    except urllib.error.URLError as e:
        raise ConnectionError(
            f"Cannot reach Ollama at {OLLAMA_URL}. Is it running? Error: {e}"
        )
