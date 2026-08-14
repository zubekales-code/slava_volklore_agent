"""
Sběr z YouTube kanálů.

Dvoukrokově, ať se zbytečně neplýtvá zdarma kreditem u Supadata:
  1. Nová videa na kanálu se zjistí přes nativní YouTube RSS feed
     (funguje spolehlivě i ze serveru, ukazuje posledních ~15 videí).
  2. Teprve pro tahle konkrétní videa se zavolá Supadata a stáhne přepis.

Pokud se přepis nepodaří stáhnout (např. došel měsíční zdarma kredit),
video se do newsletteru přesto zahrne -- jen bez plného přepisu, agent
při psaní pracuje aspoň s titulkem.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from time import mktime

import feedparser
import requests

from config_loader import Secrets

logger = logging.getLogger("collect_youtube")

YOUTUBE_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
SUPADATA_TRANSCRIPT_URL = "https://api.supadata.ai/v1/youtube/transcript"


def _fetch_transcript(video_id: str) -> str | None:
    if not Secrets.SUPADATA_API_KEY:
        return None
    try:
        resp = requests.get(
            SUPADATA_TRANSCRIPT_URL,
            params={"videoId": video_id},
            headers={"x-api-key": Secrets.SUPADATA_API_KEY},
            timeout=25,
        )
        if resp.status_code != 200:
            logger.info("Supadata: přepis nedostupný pro %s (status %s)", video_id, resp.status_code)
            return None
        data = resp.json()
        segments = data.get("content", [])
        return " ".join(seg.get("text", "") for seg in segments).strip() or None
    except requests.RequestException as e:
        logger.warning("Supadata volání selhalo pro %s: %s", video_id, e)
        return None


def collect_youtube_items(channels: list[dict], lookback_hours: int,
                           max_new_per_channel: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    results: list[dict] = []

    for channel in channels:
        name = channel.get("name", "?")
        channel_id = channel.get("channel_id", "")
        if not channel_id:
            continue

        feed_url = YOUTUBE_FEED_URL.format(channel_id=channel_id)
        try:
            resp = requests.get(
                feed_url, timeout=20,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                                        "Chrome/128.0.0.0 Safari/537.36"},
            )
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
        except Exception as e:  # noqa: BLE001
            logger.warning("YouTube kanál přeskočen (%s): %s", name, e)
            continue

        new_count = 0
        for entry in parsed.entries:
            if new_count >= max_new_per_channel:
                break

            published = None
            if getattr(entry, "published_parsed", None):
                published = datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
            if published and published < cutoff:
                continue

            video_url = entry.get("link", "")
            video_id = entry.get("yt_videoid", "") or video_url.rsplit("=", 1)[-1]
            title = entry.get("title", "").strip()
            if not video_url or not title:
                continue

            transcript = _fetch_transcript(video_id)

            results.append({
                "url": video_url,
                "title": title,
                "source": f"YouTube: {name}",
                "category": "YouTube",
                "published_at": published.isoformat() if published else None,
                "summary": (transcript or "")[:500],
                "full_text": transcript,  # může být None -- ošetřeno dál v pipeline
            })
            new_count += 1

    logger.info("YouTube sběr: %d nových videí z %d kanálů", len(results), len(channels))
    return results
