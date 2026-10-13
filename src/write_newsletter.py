"""
Krok 5: psaní finálního textu newsletteru (denní nebo týdenní verze).
"""

from __future__ import annotations

import logging
import re

import markdown as md

from config_loader import load_prompt
from openai_client import complete_text

logger = logging.getLogger("write_newsletter")

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="cs">
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, Helvetica, Arial, sans-serif;
             max-width: 640px; margin: 0 auto; padding: 24px; color: #111827;
             line-height: 1.55;">
{content}
<hr style="margin-top:32px; border:none; border-top:1px solid #E5E7EB;">
<p style="font-size:12px; color:#6B7280;">
  Sláva / Volklore Agent — automaticky vygenerováno, {mode_label}.
</p>
</body>
</html>
"""


def _source_link(item: dict) -> str:
    """Hotový markdown odkaz [Název zdroje](URL) -- model ho má jen zkopírovat."""
    name = (item.get("source") or "zdroj").replace("[", "(").replace("]", ")")
    return f"[{name}]({item['url']})"


def _items_to_context(items: list[dict]) -> str:
    parts = []
    for item in items:
        text = item.get("full_text") or item.get("summary") or ""
        note = item.get("fulltext_note", "")
        parts.append(
            f"### {item['title']}\n"
            f"Zdroj: {item.get('source', '')} | Kategorie: {item.get('category', '')}\n"
            f"Odkaz: {item['url']}\n"
            f"HOTOVÝ ODKAZ (zkopíruj doslova pod zprávu): {_source_link(item)}\n"
            + (f"Poznámka: {note}\n" if note else "")
            + f"\n{text}\n"
        )
    return "\n---\n".join(parts)


def _check_links(text: str, items: list[dict]) -> None:
    """Jen kontrola a zápis do logu -- nic v textu nemění."""
    known = {i["url"].rstrip("/") for i in items}
    found = re.findall(r"\]\((https?://[^)\s]+)\)", text)
    unknown = [u for u in found if u.rstrip("/") not in known]
    used = {u.rstrip("/") for u in found} & known
    logger.info("Odkazy v newsletteru: %d celkem, %d unikátních ze vstupu.",
                len(found), len(used))
    if unknown:
        logger.warning("Newsletter obsahuje %d odkazů, které nejsou ve vstupních "
                       "položkách (možná vymyšlené): %s", len(unknown), unknown[:5])
    if not found:
        logger.warning("Newsletter neobsahuje ŽÁDNÝ odkaz na zdroj!")


def write_newsletter(items: list[dict], mode: str, writer_model: str) -> tuple[str, str]:
    """mode = 'daily' nebo 'weekly'. Vrací (markdown_text, html_text)."""
    prompt_name = "daily_writer" if mode == "daily" else "weekly_writer"
    system_prompt = load_prompt(prompt_name)

    context = _items_to_context(items)
    user_content = (
        f"Tady je {len(items)} položek vybraných za dané období. "
        "Napiš newsletter podle instrukcí výše.\n\n" + context
    )

    # Denní verze má cíl 1500 slov, max 2000 (~10-12 min čtení); týdenní má
    # mnohem víc vstupního kontextu (desítky článků) a "reasoning" modely
    # (gpt-5.6+) spotřebovávají část stropu na neviditelné "přemýšlení" ještě
    # PŘED napsáním viditelného textu -- pokud je strop moc nízký, model
    # může vyčerpat celý limit na přemýšlení a vrátit prázdný text (viz
    # incident 16. 8. 2026 u týdenní verze). Proto je strop nastavený se
    # štědrou rezervou -- nic to nestojí navíc, platí se jen za skutečně
    # vygenerované tokeny, tohle je jen pojistka proti prázdné odpovědi.
    text = complete_text(system_prompt, user_content, model=writer_model,
                          max_output_tokens=16000 if mode == "weekly" else 8000)

    if not text:
        logger.error("Psaní newsletteru selhalo (mode=%s) -- OpenAI nevrátilo text.", mode)
        text = ("Dnešní/tento týdenní newsletter se nepodařilo vygenerovat "
                "kvůli technické chybě. Zkontroluj log běhu na GitHubu.")

    _check_links(text, items)

    html_body = md.markdown(text, extensions=["nl2br"])
    # Odkazy v e-mailu: výrazná barva + podtržení (e-mailové klienty často
    # ignorují výchozí styl odkazů).
    html_body = html_body.replace(
        "<a href=", '<a style="color:#1D4ED8; text-decoration:underline;" href=')
    mode_label = "denní verze" if mode == "daily" else "týdenní shrnutí"
    html = HTML_TEMPLATE.format(content=html_body, mode_label=mode_label)

    return text, html
