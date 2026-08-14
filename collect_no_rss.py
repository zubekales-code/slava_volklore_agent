"""
Sběr obsahu z webů, které nemají (ověřené) RSS.

Postup: Jina Reader přečte stránku s výpisem novinek jako čistý text,
levný model (classifier_model) z něj vytáhne strukturovaný seznam
{titulek, odkaz}. Stejně jako u RSS -- pokud web nejde přečíst nebo
z něj nejde nic rozumného vytáhnout, prostě se přeskočí.
"""

from __future__ import annotations

import logging

import jina_client
from openai_client import complete_json

logger = logging.getLogger("collect_no_rss")

EXTRACTION_SYSTEM_PROMPT = """Dostaneš čistý text stránky s výpisem novinek
z nějakého webu (fashion/design/marketing magazín). Tvůj úkol: najít v textu
jednotlivé články/novinky a vrátit je jako JSON.

Vrať POUZE JSON ve tvaru:
{"items": [{"title": "...", "url": "..."}, ...]}

Pravidla:
- Ber jen položky, které vypadají jako skutečné články (mají smysluplný
  titulek a odkaz), ne navigační odkazy, reklamy, "přihlásit se" apod.
- Odkazy musí být plné URL (https://...). Pokud je odkaz relativní
  (začíná jen /cesta), doplň ho podle domény, kterou v textu vidíš.
- Vrať maximálně 15 nejnovějších položek.
- Pokud nenajdeš nic rozumného, vrať {"items": []}.
"""


def collect_no_rss_items(sources: list[dict], classifier_model: str) -> list[dict]:
    results: list[dict] = []

    for source in sources:
        name = source.get("name", "?")
        listing_url = source.get("listing_url", "")
        if not listing_url:
            continue

        page_text = jina_client.read_url(listing_url)
        if not page_text:
            logger.warning("Web bez RSS přeskočen (nešlo načíst): %s", name)
            continue

        # Ořízneme na rozumnou délku, ať nefouká zbytečně cenu.
        page_text = page_text[:12000]

        extracted = complete_json(
            EXTRACTION_SYSTEM_PROMPT,
            f"Zdroj: {name}\nAdresa výpisu: {listing_url}\n\nText stránky:\n{page_text}",
            model=classifier_model,
        )
        if not extracted or "items" not in extracted:
            logger.warning("Web bez RSS přeskočen (extrakce selhala): %s", name)
            continue

        for item in extracted["items"]:
            url = item.get("url", "")
            title = item.get("title", "")
            if not url or not title:
                continue
            results.append({
                "url": url,
                "title": title.strip(),
                "source": name,
                "category": source.get("category", ""),
                "published_at": None,  # u těchto zdrojů datum obvykle neznáme
                "summary": "",
            })

    logger.info("Weby bez RSS: %d položek z %d zdrojů", len(results), len(sources))
    return results
