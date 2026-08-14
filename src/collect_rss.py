"""
Sběr obsahu z RSS zdrojů (config/sources.yaml -> rss_sources).

Pokud se u nějakého zdroje nepodaří feed stáhnout nebo rozparsovat,
zdroj se jednoduše přeskočí -- run kvůli jednomu nefunkčnímu zdroji
nespadne (viz zadání: "co nešlo, ignorovat").
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from time import mktime

import feedparser
import requests

logger = logging.getLogger("collect_rss")


def _entry_datetime(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = getattr(entry, key, None)
        if value:
            return datetime.fromtimestamp(mktime(value), tz=timezone.utc)
    return None


def collect_rss_items(sources: list[dict], lookback_hours: int,
                       timeout_seconds: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    results: list[dict] = []

    for source in sources:
        name = source.get("name", "?")
        feed_url = source.get("feed_url", "")
        if not feed_url:
            continue
        try:
            resp = requests.get(
                feed_url,
                timeout=timeout_seconds,
                headers={"User-Agent": "Mozilla/5.0 (compatible; VolkloreAgent/1.0)"},
            )
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
        except Exception as e:  # noqa: BLE001 -- záměrně chytáme cokoliv, ať run pokračuje
            logger.warning("RSS přeskočeno (%s): %s", name, e)
            continue

        if parsed.bozo and not parsed.entries:
            logger.warning("RSS nešlo rozparsovat (%s): %s", name,
                            getattr(parsed, "bozo_exception", "neznámá chyba"))
            continue

        for entry in parsed.entries:
            published = _entry_datetime(entry)
            if published and published < cutoff:
                continue
            url = entry.get("link", "")
            if not url:
                continue
            results.append({
                "url": url,
                "title": entry.get("title", "").strip() or "(bez titulku)",
                "source": name,
                "category": source.get("category", ""),
                "published_at": published.isoformat() if published else None,
                "summary": (entry.get("summary", "") or "")[:2000],
            })

    logger.info("RSS sběr: %d položek z %d zdrojů", len(results), len(sources))
    return results
