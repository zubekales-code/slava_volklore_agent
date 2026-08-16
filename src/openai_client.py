"""
Tenká vrstva nad OpenAI API. Modely se neřeší tady, ale v config/settings.yaml
(models.classifier_model / models.writer_model) -- ať se dají měnit bez
zásahu do kódu.
"""

from __future__ import annotations

import json
import logging

from openai import OpenAI

from config_loader import Secrets

logger = logging.getLogger("openai_client")

_client: OpenAI | None = None

# Sleduje spotřebu tokenů za celý běh, ať se dá na konci vypsat skutečná
# cena místo odhadu. Reset na začátku každého spuštění (modul se načte znovu).
_usage: dict[str, dict[str, int]] = {}


def _track_usage(model: str, usage) -> None:
    if usage is None:
        return
    bucket = _usage.setdefault(model, {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0})
    bucket["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
    bucket["completion_tokens"] += getattr(usage, "completion_tokens", 0) or 0
    bucket["calls"] += 1


def get_usage_summary() -> dict[str, dict[str, int]]:
    """Vrací {model: {prompt_tokens, completion_tokens, calls}} za tenhle běh."""
    return _usage


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=Secrets.OPENAI_API_KEY)
    return _client


def complete_json(system_prompt: str, user_content: str, model: str) -> dict | list | None:
    """Zavolá model a očekává zpět validní JSON. Vrací None při chybě.

    Pozn.: gpt-5.6 a novější "reasoning" modely nepodporují vlastní
    'temperature' (jen výchozí hodnotu), proto se tu neposílá vůbec."""
    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )
        _track_usage(model, resp.usage)
        raw = resp.choices[0].message.content
        return json.loads(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning("OpenAI JSON volání selhalo: %s", e)
        return None


def complete_text(system_prompt: str, user_content: str, model: str,
                   max_output_tokens: int = 4000) -> str | None:
    """Zavolá model a vrátí prostý text (pro psaní newsletteru).

    Pozn.: gpt-5.6 a novější "reasoning" modely nepodporují vlastní
    'temperature' a místo 'max_tokens' vyžadují 'max_completion_tokens'."""
    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_completion_tokens=max_output_tokens,
        )
        _track_usage(model, resp.usage)
        content = resp.choices[0].message.content
        if not content:
            # Prázdný text s HTTP 200 obvykle znamená, že "reasoning" model
            # spotřeboval celý max_completion_tokens strop na neviditelné
            # přemýšlení ještě před napsáním viditelného textu. Vypíšeme
            # detaily rovnou do logu, ať se to příště nemusí znovu dohledávat.
            finish_reason = resp.choices[0].finish_reason
            reasoning_tokens = None
            details = getattr(resp.usage, "completion_tokens_details", None)
            if details is not None:
                reasoning_tokens = getattr(details, "reasoning_tokens", None)
            logger.warning(
                "OpenAI vrátilo prázdný text (model=%s, finish_reason=%s, "
                "reasoning_tokens=%s, max_completion_tokens=%d) -- pravděpodobně "
                "došel strop na 'přemýšlení' modelu ještě před napsáním "
                "viditelného textu. Zkus zvýšit max_output_tokens.",
                model, finish_reason, reasoning_tokens, max_output_tokens,
            )
            return None
        return content
    except Exception as e:  # noqa: BLE001
        logger.warning("OpenAI textové volání selhalo: %s", e)
        return None

