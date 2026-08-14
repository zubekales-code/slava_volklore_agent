"""
Hlavní vstupní bod. Spouští se buď automaticky přes GitHub Actions
(denně v 8:00 / týdně v neděli v 8:00), nebo ručně tlačítkem
"Run workflow" na GitHubu.

Použití:
    python src/main.py --mode daily
    python src/main.py --mode weekly

Pipeline (viz shrnutí projektu, kroky 1-6):
    1. Sběr obsahu (RSS + weby bez RSS + YouTube)   -> uložení do Supabase
    2. Deduplikace                                   -> Supabase to řeší samo
    3. Oskórování relevance                          -> levný model
    4. Dotažení plného textu top položek              -> Jina (+ dohledání
                                                          u placeného obsahu)
    5. Napsání newsletteru                            -> výkonnější model
    6. Odeslání e-mailem                              -> Resend
"""

from __future__ import annotations

import argparse
import logging
import sys

from config_loader import load_sources, load_settings, Secrets
import storage
from collect_rss import collect_rss_items
from collect_no_rss import collect_no_rss_items
from collect_youtube import collect_youtube_items
from scoring import score_items
from fetch_fulltext import enrich_items
from write_newsletter import write_newsletter
from send_email import send_newsletter_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


def run_collection(sources: dict, settings: dict) -> None:
    logger.info("=== Krok 1: sběr obsahu ===")
    lookback = settings["collection"]["lookback_hours"]
    timeout = settings["collection"]["per_source_timeout_seconds"]

    rss_items = collect_rss_items(sources.get("rss_sources", []), lookback, timeout)
    no_rss_items = collect_no_rss_items(
        sources.get("no_rss_sources", []),
        classifier_model=settings["models"]["classifier_model"],
    )
    yt_channels = sources.get("youtube_channels", [])
    yt_items = collect_youtube_items(
        yt_channels, lookback,
        max_new_per_channel=settings["supadata"]["max_new_videos_per_channel_per_run"],
    )

    all_items = rss_items + no_rss_items + yt_items
    logger.info("Celkem nasbíráno %d položek, ukládám do Supabase...", len(all_items))
    storage.upsert_items(all_items)


def run_scoring(sources: dict, settings: dict) -> None:
    logger.info("=== Krok 3: oskórování relevance ===")
    lookback = settings["collection"]["lookback_hours"]
    unscored = storage.get_unscored_items(lookback)
    if not unscored:
        logger.info("Žádné nové neoskórované položky.")
        return
    scored = score_items(unscored, classifier_model=settings["models"]["classifier_model"])
    storage.update_item_scores(scored)


def run_digest(mode: str, settings: dict) -> None:
    logger.info("=== Kroky 4-6: příprava a odeslání (%s) ===", mode)
    sel = settings["selection"]
    lookback = sel["daily_digest_lookback_hours"] if mode == "daily" else sel["weekly_digest_lookback_hours"]
    max_items = sel["daily_max_items"] if mode == "daily" else sel["weekly_max_items"]

    items = storage.get_items_for_digest(
        mode=mode, lookback_hours=lookback,
        min_score=sel["min_relevance_score"], max_items=max_items,
    )
    if not items:
        logger.warning("Žádné položky pro %s digest -- e-mail se neposílá.", mode)
        return

    logger.info("Dotahuji plný text pro %d položek...", len(items))
    items = enrich_items(items, word_threshold=sel["paywall_snippet_word_threshold"])

    logger.info("Píšu newsletter (%s)...", mode)
    _, html = write_newsletter(items, mode=mode, writer_model=settings["models"]["writer_model"])

    email_cfg = settings["email"]
    ok = send_newsletter_email(
        html, mode=mode,
        recipient=email_cfg["recipient"],
        sender_name=email_cfg["sender_name"],
        sender_email=email_cfg["sender_email"],
    )
    if ok:
        storage.mark_items_included([item["url"] for item in items], mode=mode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sláva/Volklore newsletter agent")
    parser.add_argument("--mode", choices=["daily", "weekly"], required=True)
    parser.add_argument("--skip-collection", action="store_true",
                         help="Přeskočí sběr nového obsahu (jen pro ladění).")
    args = parser.parse_args()

    missing = Secrets.validate()
    if missing:
        logger.error("Chybí potřebné klíče v prostředí (GitHub Secrets): %s", ", ".join(missing))
        return 1

    sources = load_sources()
    settings = load_settings()

    if not args.skip_collection:
        run_collection(sources, settings)
        run_scoring(sources, settings)

    run_digest(args.mode, settings)

    logger.info("Hotovo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
