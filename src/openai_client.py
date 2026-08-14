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
        return resp.choices[0].message.content
    except Exception as e:  # noqa: BLE001
        logger.warning("OpenAI textové volání selhalo: %s", e)
        return None
