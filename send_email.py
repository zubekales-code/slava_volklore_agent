"""
Krok 6: odeslání hotového newsletteru e-mailem přes Resend.
"""

from __future__ import annotations

import logging
from datetime import datetime

import requests

from config_loader import Secrets

logger = logging.getLogger("send_email")

RESEND_URL = "https://api.resend.com/emails"


def send_newsletter_email(html: str, mode: str, recipient: str,
                           sender_name: str, sender_email: str) -> bool:
    today = datetime.now().strftime("%-d. %-m. %Y")
    subject_prefix = "Denní" if mode == "daily" else "Týdenní"
    subject = f"{subject_prefix} radar Sláva/Volklore — {today}"

    payload = {
        "from": f"{sender_name} <{sender_email}>",
        "to": [recipient],
        "subject": subject,
        "html": html,
    }
    headers = {
        "Authorization": f"Bearer {Secrets.RESEND_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(RESEND_URL, headers=headers, json=payload, timeout=20)
        if resp.status_code not in (200, 201):
            logger.error("Odeslání e-mailu selhalo (status %s): %s",
                         resp.status_code, resp.text[:300])
            return False
        logger.info("E-mail odeslán (%s) na %s", mode, recipient)
        return True
    except requests.RequestException as e:
        logger.error("Odeslání e-mailu selhalo: %s", e)
        return False
