"""
Ukládání nasbíraných položek do Supabase a deduplikace.

Používá se přímo REST rozhraní Supabase (PostgREST), takže stačí knihovna
'requests' -- žádná další závislost navíc. Tabulka 'items' se musí v Supabase
založit předem -- SQL příkaz je v sql/schema.sql (návod v README).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from config_loader import Secrets

logger = logging.getLogger("storage")

TABLE = "items"


def _headers() -> dict:
    return {
        "apikey": Secrets.SUPABASE_KEY,
        "Authorization": f"Bearer {Secrets.SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    url = Secrets.SUPABASE_URL.strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        # Ochrana proti časté chybě: SUPABASE_URL vyplněný bez "https://" vpředu.
        url = "https://" + url
    return f"{url}/rest/v1/{TABLE}"


def upsert_items(items: list[dict[str, Any]]) -> int:
    """Vloží nové položky. Duplicity (podle 'url') se tiše ignorují.
    Vrací počet položek, které se skutečně pokusily odeslat (ne nutně
    kolik jich bylo nových -- to Supabase v tichém režimu nehlásí)."""
    if not items:
        return 0
    headers = _headers()
    # 'resolution=ignore-duplicates' = když už url existuje, řádek se přeskočí
    # místo aby to spadlo na chybu unikátnosti.
    headers["Prefer"] = "resolution=ignore-duplicates,return=minimal"
    try:
        resp = requests.post(_base_url(), headers=headers, json=items, timeout=30)
        if resp.status_code not in (200, 201, 204):
            logger.warning("Supabase upsert: neočekávaný status %s: %s",
                            resp.status_code, resp.text[:300])
        return len(items)
    except requests.RequestException as e:
        logger.warning("Supabase upsert selhal: %s", e)
        return 0


def get_unscored_items(lookback_hours: int) -> list[dict]:
    """Vrátí položky za posledních N hodin, které ještě nemají relevance_score."""
    since = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()
    params = {
        "select": "*",
        "relevance_score": "is.null",
        "created_at": f"gte.{since}",
        "order": "created_at.desc",
        "limit": "500",
    }
    try:
        resp = requests.get(_base_url(), headers=_headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.warning("Supabase čtení (unscored) selhalo: %s", e)
        return []


def update_item_scores(scored: list[dict]) -> None:
    """scored = [{'url':..., 'relevance_score':..., 'category':...,
    'is_paywalled_snippet':...}, ...]"""
    for item in scored:
        try:
            params = {"url": f"eq.{item['url']}"}
            body = {
                "relevance_score": item.get("relevance_score"),
                "category": item.get("category"),
                "is_paywalled_snippet": item.get("is_paywalled_snippet", False),
            }
            requests.patch(_base_url(), headers=_headers(), params=params,
                            json=body, timeout=15)
        except requests.RequestException as e:
            logger.warning("Nepodařilo se uložit skóre pro %s: %s", item.get("url"), e)


def get_items_for_digest(mode: str, lookback_hours: int, min_score: int,
                          max_items: int) -> list[dict]:
    """mode = 'daily' nebo 'weekly'. Vrátí nejlépe hodnocené položky."""
    since = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()
    included_col = "included_in_daily" if mode == "daily" else "included_in_weekly"
    params = {
        "select": "*",
        "relevance_score": f"gte.{min_score}",
        "created_at": f"gte.{since}",
        included_col: "eq.false",
        "order": "relevance_score.desc",
        "limit": str(max_items),
    }
    try:
        resp = requests.get(_base_url(), headers=_headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.warning("Supabase čtení (digest) selhalo: %s", e)
        return []


def mark_items_included(urls: list[str], mode: str) -> None:
    included_col = "included_in_daily" if mode == "daily" else "included_in_weekly"
    for url in urls:
        try:
            params = {"url": f"eq.{url}"}
            requests.patch(_base_url(), headers=_headers(), params=params,
                            json={included_col: True}, timeout=15)
        except requests.RequestException as e:
            logger.warning("Nepodařilo se označit %s jako zahrnuté: %s", url, e)


def update_full_text(url: str, full_text: str) -> None:
    try:
        params = {"url": f"eq.{url}"}
        requests.patch(_base_url(), headers=_headers(), params=params,
                        json={"full_text": full_text}, timeout=15)
    except requests.RequestException as e:
        logger.warning("Nepodařilo se uložit plný text pro %s: %s", url, e)
