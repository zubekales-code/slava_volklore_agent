"""
Tenká vrstva nad Jina Reader (r.jina.ai) a Jina Search (s.jina.ai).

Funguje bez API klíče (nižší rychlostní limit, pro náš denní objem stačí).
Pokud by bylo potřeba víc, stačí do .env / GitHub Secrets doplnit
JINA_API_KEY a doplnit header 'Authorization' -- kód na to je připravený.
"""

from __future__ import annotations

import logging

import requests

from config_loader import Secrets

logger = logging.getLogger("jina_client")

READER_BASE = "https://r.jina.ai/"
SEARCH_BASE = "https://s.jina.ai/"


def _headers() -> dict:
    headers = {"Accept": "text/plain"}
    if Secrets.JINA_API_KEY:
        headers["Authorization"] = f"Bearer {Secrets.JINA_API_KEY}"
    return headers


def read_url(url: str, timeout_seconds: int = 25) -> str | None:
    """Vrátí čistý text stránky, nebo None při chybě."""
    try:
        resp = requests.get(READER_BASE + url, headers=_headers(), timeout=timeout_seconds)
        if resp.status_code != 200:
            logger.warning("Jina Reader chyba (%s) pro %s", resp.status_code, url)
            return None
        return resp.text
    except requests.RequestException as e:
        logger.warning("Jina Reader selhal pro %s: %s", url, e)
        return None


def search(query: str, timeout_seconds: int = 25) -> str | None:
    """Vrátí čistý text výsledků vyhledávání pro dotaz, nebo None při chybě."""
    try:
        resp = requests.get(SEARCH_BASE + query, headers=_headers(), timeout=timeout_seconds)
        if resp.status_code != 200:
            logger.warning("Jina Search chyba (%s) pro dotaz '%s'", resp.status_code, query)
            return None
        return resp.text
    except requests.RequestException as e:
        logger.warning("Jina Search selhal pro '%s': %s", query, e)
        return None
