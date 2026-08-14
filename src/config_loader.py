"""
Načítání konfiguračních souborů (config/*.yaml a config/prompts/*.md).

Tenhle soubor by se neměl muset upravovat -- veškeré "lidské" nastavení
žije v config/sources.yaml, config/settings.yaml a config/prompts/*.md.
"""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
PROMPTS_DIR = CONFIG_DIR / "prompts"


@lru_cache(maxsize=1)
def load_sources() -> dict:
    with open(CONFIG_DIR / "sources.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_settings() -> dict:
    with open(CONFIG_DIR / "settings.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=8)
def load_prompt(name: str) -> str:
    """name je bez přípony, např. 'classifier', 'daily_writer', 'weekly_writer'."""
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")


class Secrets:
    """Tajné klíče se čtou z proměnných prostředí (GitHub Actions Secrets),
    nikdy nejsou v repozitáři. Viz README -> nastavení GitHub Secrets."""

    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
    SUPADATA_API_KEY = os.environ.get("SUPADATA_API_KEY", "")
    JINA_API_KEY = os.environ.get("JINA_API_KEY", "")  # volitelné, funguje i bez klíče

    @classmethod
    def validate(cls) -> list[str]:
        """Vrátí seznam chybějících povinných klíčů (Jina je nepovinná)."""
        required = {
            "OPENAI_API_KEY": cls.OPENAI_API_KEY,
            "SUPABASE_URL": cls.SUPABASE_URL,
            "SUPABASE_KEY": cls.SUPABASE_KEY,
            "RESEND_API_KEY": cls.RESEND_API_KEY,
            "SUPADATA_API_KEY": cls.SUPADATA_API_KEY,
        }
        return [name for name, value in required.items() if not value]
