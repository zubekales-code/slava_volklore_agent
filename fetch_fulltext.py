"""
Dotažení plného textu u položek vybraných k zpracování (Krok 4 v shrnutí
projektu).

Logika pro placený obsah (BoF, Vogue Business apod.):
  1. Zkusí se stáhnout plný text přes Jina Reader.
  2. Pokud vyjde jen krátký útržek (méně slov než
     'paywall_snippet_word_threshold'), zkusí se přes Jina Search dohledat
     doplňkový kontext na stejné téma jinde na webu.
  3. Zpráva se zařadí VŽDY -- v horším případě jen jako krátká zmínka
     s odkazem na originál, nikdy se kvůli placenému obsahu úplně nevyřadí.
"""

from __future__ import annotations

import logging

import jina_client

logger = logging.getLogger("fetch_fulltext")


def enrich_item_with_fulltext(item: dict, word_threshold: int) -> dict:
    # YouTube položky mají full_text (přepis) už od sběru -- není co dotahovat.
    if item.get("full_text"):
        return item

    url = item["url"]
    full_text = jina_client.read_url(url)

    if not full_text:
        # Web nešel načíst vůbec -- necháme jen to, co už máme (titulek/summary),
        # a poznamenáme to, aby to bylo vidět při psaní newsletteru.
        item["full_text"] = None
        item["fulltext_note"] = "Plný text se nepodařilo načíst, k dispozici jen titulek/perex."
        return item

    word_count = len(full_text.split())

    if word_count < word_threshold:
        # Vypadá to jako placený obsah / useknutý snippet -> zkusíme dohledat víc.
        logger.info("Krátký text (%d slov) u %s, zkouším dohledat kontext jinde.",
                     word_count, url)
        search_results = jina_client.search(item["title"])
        if search_results:
            full_text = (
                f"[Původní zdroj poskytl jen krátký úryvek:]\n{full_text}\n\n"
                f"[Doplňkový kontext dohledaný jinde na webu:]\n{search_results[:3000]}"
            )
            item["fulltext_note"] = "Sestaveno z krátkého úryvku + doplňkového dohledání."
        else:
            item["fulltext_note"] = "Jen krátký úryvek, doplňkový kontext se nepodařilo najít."

    item["full_text"] = full_text[:6000]  # ořez, ať to zbytečně nefouká cenu psaní
    return item


def enrich_items(items: list[dict], word_threshold: int) -> list[dict]:
    enriched = []
    for item in items:
        try:
            enriched.append(enrich_item_with_fulltext(item, word_threshold))
        except Exception as e:  # noqa: BLE001
            logger.warning("Dotažení textu selhalo pro %s: %s", item.get("url"), e)
            item["full_text"] = None
            enriched.append(item)
    return enriched
