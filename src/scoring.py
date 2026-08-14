"""
Krok 3: oskórování relevance nasbíraných položek levným modelem.

Posílá se dávkově (víc položek najednou), ať se to zbytečně neprodraží
a nezdržuje. Pokud se pro nějakou dávku odpověď nepovede rozparsovat,
ta dávka se prostě přeskočí -- příslušné položky zůstanou bez skóre
a do dalšího výběru se nedostanou (nejsou tím pádem ztracené navždy,
příští běh je zkusí znovu, pokud jsou pořád v okně lookback_hours).
"""

from __future__ import annotations

import logging

from config_loader import load_prompt
from openai_client import complete_json

logger = logging.getLogger("select")

BATCH_SIZE = 40


def score_items(items: list[dict], classifier_model: str) -> list[dict]:
    system_prompt = load_prompt("classifier")
    scored: list[dict] = []

    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i:i + BATCH_SIZE]
        payload_lines = []
        for idx, item in enumerate(batch):
            payload_lines.append(
                f"{idx}. TITULEK: {item['title']}\n"
                f"   ZDROJ: {item.get('source', '')}\n"
                f"   POPIS: {(item.get('summary') or '')[:300]}"
            )
        user_content = (
            "Zde je " + str(len(batch)) + " položek k oskórování. "
            "Vrať JSON: {\"results\": [{\"index\": 0, \"relevance_score\": N, "
            "\"category\": \"...\", \"is_paywalled_snippet\": true/false}, ...]} "
            "-- pole 'results' musí mít stejný počet a pořadí jako vstup.\n\n"
            + "\n\n".join(payload_lines)
        )

        result = complete_json(system_prompt, user_content, model=classifier_model)
        if not result or "results" not in result:
            logger.warning("Oskórování dávky %d–%d selhalo, přeskočeno.", i, i + len(batch))
            continue

        for r in result["results"]:
            idx = r.get("index")
            if idx is None or idx >= len(batch):
                continue
            source_item = batch[idx]
            scored.append({
                "url": source_item["url"],
                "relevance_score": r.get("relevance_score"),
                "category": r.get("category", source_item.get("category", "")),
                "is_paywalled_snippet": r.get("is_paywalled_snippet", False),
            })

    logger.info("Oskórováno %d z %d nasbíraných položek", len(scored), len(items))
    return scored
