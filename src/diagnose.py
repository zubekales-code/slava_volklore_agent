"""
DIAGNOSTIKA -- otestuje všechny externí služby najednou a vypíše přehled.

Spouští se stejným tlačítkem jako newsletter (Actions -> Run workflow),
jen se v rozbalovacím seznamu vybere "diagnostics".

Nic neodesílá kromě jednoho testovacího e-mailu a nic trvale nezapisuje
(testovací řádek v databázi se hned zase smaže).

Účel: místo objevování chyb po jedné (jeden běh = jedna chyba) zjistit
všechny problémy naráz.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone

import requests

from config_loader import load_sources, load_settings, Secrets

RESULTS: list[tuple[str, str, str]] = []  # (název testu, stav, detail)

OK = "OK"
FAIL = "CHYBA"
WARN = "POZOR"


def record(name: str, status: str, detail: str = "") -> None:
    RESULTS.append((name, status, detail))
    icon = {OK: "[ OK  ]", FAIL: "[CHYBA]", WARN: "[POZOR]"}[status]
    print(f"{icon} {name}" + (f" -- {detail}" if detail else ""), flush=True)


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}", flush=True)


# ---------------------------------------------------------------- 1. KLÍČE
def check_secrets() -> None:
    section("1. KLÍČE (GitHub Secrets)")
    checks = {
        "OPENAI_API_KEY": Secrets.OPENAI_API_KEY,
        "SUPABASE_URL": Secrets.SUPABASE_URL,
        "SUPABASE_KEY": Secrets.SUPABASE_KEY,
        "RESEND_API_KEY": Secrets.RESEND_API_KEY,
        "SUPADATA_API_KEY": Secrets.SUPADATA_API_KEY,
    }
    for name, value in checks.items():
        if not value:
            record(f"Klíč {name}", FAIL, "chybí / je prázdný")
            continue
        # Kontrola častých překlepů: mezery, uvozovky, konce řádků.
        problems = []
        if value != value.strip():
            problems.append("obsahuje mezeru/enter na začátku nebo konci")
        if value.startswith(('"', "'")) or value.endswith(('"', "'")):
            problems.append("obsahuje uvozovky")
        if name == "SUPABASE_URL":
            if not value.strip().startswith("https://"):
                problems.append("nezačíná na https://")
            if "/rest/v1" in value:
                problems.append("obsahuje /rest/v1 navíc (má být jen doména)")
        if problems:
            record(f"Klíč {name}", WARN, "; ".join(problems))
        else:
            record(f"Klíč {name}", OK, f"vyplněn ({len(value)} znaků)")

    if not Secrets.JINA_API_KEY:
        record("Klíč JINA_API_KEY", OK, "nevyplněn -- to je v pořádku, je nepovinný")


# --------------------------------------------------------------- 2. OPENAI
def check_openai(settings: dict) -> None:
    section("2. OPENAI")
    if not Secrets.OPENAI_API_KEY:
        record("OpenAI", FAIL, "chybí klíč, test přeskočen")
        return

    try:
        from openai import OpenAI
        import openai as openai_pkg
        record("OpenAI knihovna", OK, f"verze {openai_pkg.__version__}")
    except Exception as e:  # noqa: BLE001
        record("OpenAI knihovna", FAIL, str(e))
        return

    try:
        client = OpenAI(api_key=Secrets.OPENAI_API_KEY)
    except Exception as e:  # noqa: BLE001
        record("OpenAI připojení", FAIL, str(e))
        return

    # Které modely jsou na TOMHLE účtu vůbec dostupné.
    available: set[str] = set()
    try:
        models = client.models.list()
        available = {m.id for m in models.data}
        record("OpenAI seznam modelů", OK, f"účet vidí {len(available)} modelů")
        interesting = sorted(m for m in available if m.startswith(("gpt-5", "gpt-4")))
        if interesting:
            print("        Dostupné GPT modely na tomto účtu:", flush=True)
            for m in interesting:
                print(f"          - {m}", flush=True)
    except Exception as e:  # noqa: BLE001
        record("OpenAI seznam modelů", WARN, f"nešlo načíst: {e}")

    # Ostrý test obou nakonfigurovaných modelů.
    for role, key in (("třídič", "classifier_model"), ("spisovatel", "writer_model")):
        model = settings["models"][key]
        if available and model not in available:
            record(f"Model '{model}' ({role})", FAIL,
                    "tenhle model na účtu NEEXISTUJE -- oprav 'models." + key
                    + "' v config/settings.yaml podle seznamu výše")
            continue
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Odpovídej pouze validním JSON."},
                    {"role": "user", "content": 'Vrať přesně: {"test": "ok"}'},
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=2000,
            )
            content = resp.choices[0].message.content
            json.loads(content)
            record(f"Model '{model}' ({role})", OK, "volání i JSON odpověď fungují")
        except Exception as e:  # noqa: BLE001
            record(f"Model '{model}' ({role})", FAIL, str(e)[:250])


# ------------------------------------------------------------- 3. SUPABASE
def check_supabase() -> None:
    section("3. SUPABASE (databáze)")
    if not (Secrets.SUPABASE_URL and Secrets.SUPABASE_KEY):
        record("Supabase", FAIL, "chybí URL nebo klíč, test přeskočen")
        return

    import storage

    base = storage._base_url()
    headers = storage._headers()

    # Existuje tabulka a jde číst?
    try:
        resp = requests.get(base, headers=headers, params={"select": "url", "limit": "1"}, timeout=20)
        if resp.status_code == 200:
            record("Supabase čtení", OK, "tabulka 'items' existuje a je čitelná")
        elif resp.status_code == 404:
            record("Supabase čtení", FAIL,
                    "tabulka 'items' NEEXISTUJE -- spusť obsah sql/schema.sql "
                    "v Supabase (SQL Editor -> New query -> Run)")
            return
        else:
            record("Supabase čtení", FAIL, f"status {resp.status_code}: {resp.text[:200]}")
            return
    except Exception as e:  # noqa: BLE001
        record("Supabase čtení", FAIL, str(e)[:250])
        return

    # Kolik už je uvnitř dat?
    try:
        resp = requests.get(base, headers={**headers, "Prefer": "count=exact"},
                             params={"select": "url", "limit": "1"}, timeout=20)
        total = resp.headers.get("content-range", "?").split("/")[-1]
        record("Supabase obsah", OK, f"v tabulce je aktuálně {total} položek")
    except Exception:  # noqa: BLE001
        pass

    # Zápis dvou různě tvarovaných položek najednou -- přesně to, co dřív padalo
    # na "All object keys must match".
    marker = f"https://diagnostika.test/{datetime.now(timezone.utc).timestamp()}"
    marker2 = marker + "-b"
    try:
        test_items = [
            {"url": marker, "title": "Diagnostika A", "source": "diagnostika"},
            {"url": marker2, "title": "Diagnostika B", "source": "diagnostika",
             "full_text": "text navíc, který první položka nemá"},
        ]
        written = storage.upsert_items(test_items)
        if written:
            resp = requests.get(base, headers=headers,
                                 params={"select": "url", "url": f"like.https://diagnostika.test/*"},
                                 timeout=20)
            found = len(resp.json()) if resp.status_code == 200 else 0
            if found >= 2:
                record("Supabase zápis", OK, "zápis různě tvarovaných položek funguje")
            else:
                record("Supabase zápis", FAIL,
                        f"zápis neprošel (nalezeno {found} z 2 testovacích řádků)")
        else:
            record("Supabase zápis", FAIL, "upsert_items vrátil 0")
    except Exception as e:  # noqa: BLE001
        record("Supabase zápis", FAIL, str(e)[:250])

    # Úklid testovacích řádků.
    try:
        requests.delete(base, headers=headers,
                         params={"url": "like.https://diagnostika.test/*"}, timeout=20)
        record("Supabase úklid", OK, "testovací řádky smazány")
    except Exception as e:  # noqa: BLE001
        record("Supabase úklid", WARN, f"testovací řádky se nepodařilo smazat: {e}")


# ---------------------------------------------------------------- 4. RESEND
def check_resend(settings: dict) -> None:
    section("4. RESEND (odesílání e-mailu)")
    if not Secrets.RESEND_API_KEY:
        record("Resend", FAIL, "chybí klíč, test přeskočen")
        return

    email_cfg = settings["email"]
    payload = {
        "from": f"{email_cfg['sender_name']} <{email_cfg['sender_email']}>",
        "to": [email_cfg["recipient"]],
        "subject": "Diagnostika Sláva/Volklore -- test odesílání",
        "html": "<p>Tohle je testovací e-mail z diagnostiky. "
                "Pokud ti dorazil, odesílání funguje správně.</p>",
    }
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {Secrets.RESEND_API_KEY}",
                     "Content-Type": "application/json"},
            json=payload, timeout=20,
        )
        if resp.status_code in (200, 201):
            record("Resend odeslání", OK,
                    f"testovací e-mail odeslán na {email_cfg['recipient']} "
                    "-- zkontroluj schránku VČETNĚ spamu")
        else:
            record("Resend odeslání", FAIL, f"status {resp.status_code}: {resp.text[:250]}")
    except Exception as e:  # noqa: BLE001
        record("Resend odeslání", FAIL, str(e)[:250])


# -------------------------------------------------------------- 5. SUPADATA
def check_supadata(sources: dict) -> None:
    section("5. SUPADATA (přepisy YouTube)")
    if not Secrets.SUPADATA_API_KEY:
        record("Supadata", FAIL, "chybí klíč, test přeskočen")
        return

    import feedparser
    channels = sources.get("youtube_channels", [])
    if not channels:
        record("Supadata", WARN, "v konfiguraci nejsou žádné YouTube kanály")
        return

    channel = channels[0]
    try:
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel['channel_id']}"
        r = requests.get(feed_url, timeout=20,
                          headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                                  "Chrome/128.0.0.0 Safari/537.36"})
        r.raise_for_status()
        parsed = feedparser.parse(r.content)
        if not parsed.entries:
            record("YouTube feed", FAIL, f"feed kanálu {channel['name']} je prázdný")
            return
        entry = parsed.entries[0]
        video_id = entry.get("yt_videoid", "")
        record("YouTube feed", OK, f"{channel['name']}: nalezeno {len(parsed.entries)} videí")
    except Exception as e:  # noqa: BLE001
        record("YouTube feed", FAIL, str(e)[:250])
        return

    try:
        resp = requests.get("https://api.supadata.ai/v1/youtube/transcript",
                             params={"videoId": video_id},
                             headers={"x-api-key": Secrets.SUPADATA_API_KEY},
                             timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            segments = data.get("content", [])
            record("Supadata přepis", OK,
                    f"přepis staženy ({len(segments)} segmentů) pro video {video_id}")
        elif resp.status_code in (401, 403):
            record("Supadata přepis", FAIL,
                    f"status {resp.status_code} -- klíč je nejspíš neplatný: {resp.text[:150]}")
        elif resp.status_code == 429:
            record("Supadata přepis", WARN, "vyčerpán měsíční zdarma limit (100 přepisů)")
        else:
            record("Supadata přepis", WARN, f"status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:  # noqa: BLE001
        record("Supadata přepis", FAIL, str(e)[:250])


# ------------------------------------------------------------------ 6. JINA
def check_jina() -> None:
    section("6. JINA READER (čtení webů bez RSS)")
    import jina_client
    text = jina_client.read_url("https://example.com")
    if text and len(text) > 50:
        record("Jina Reader", OK, f"čtení stránky funguje ({len(text)} znaků)")
    else:
        record("Jina Reader", FAIL,
                "nepodařilo se přečíst testovací stránku "
                "(bez klíče platí nízký rychlostní limit -- zkus znovu za minutu)")


# ------------------------------------------------------------- 7. ZDROJE
def check_sources(sources: dict, settings: dict) -> None:
    section("7. ZDROJE (které RSS feedy reálně fungují)")
    timeout = settings["collection"]["per_source_timeout_seconds"]
    import feedparser

    working, broken = [], []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/128.0.0.0 Safari/537.36"}

    for source in sources.get("rss_sources", []):
        name = source["name"]
        try:
            r = requests.get(source["feed_url"], timeout=timeout, headers=headers)
            r.raise_for_status()
            parsed = feedparser.parse(r.content)
            count = len(parsed.entries)
            if count:
                working.append((name, count))
                print(f"  [ OK  ] {name}: {count} položek", flush=True)
            else:
                broken.append((name, "feed je prázdný / nešel rozparsovat"))
                print(f"  [CHYBA] {name}: prázdný feed", flush=True)
        except Exception as e:  # noqa: BLE001
            reason = str(e).split("for url")[0].strip()[:80]
            broken.append((name, reason))
            print(f"  [CHYBA] {name}: {reason}", flush=True)

    record("RSS zdroje", OK if working else FAIL,
            f"funguje {len(working)} z {len(working) + len(broken)}")
    if broken:
        print("\n  Nefunkční zdroje (skript je při běhu tiše přeskakuje):", flush=True)
        for name, reason in broken:
            print(f"    - {name}: {reason}", flush=True)


# ---------------------------------------------------------------- SOUHRN
def summary() -> int:
    section("SOUHRN")
    fails = [r for r in RESULTS if r[1] == FAIL]
    warns = [r for r in RESULTS if r[1] == WARN]
    oks = [r for r in RESULTS if r[1] == OK]

    print(f"  V pořádku: {len(oks)}", flush=True)
    print(f"  Varování:  {len(warns)}", flush=True)
    print(f"  Chyby:     {len(fails)}", flush=True)

    if fails:
        print("\n  CO JE POTŘEBA OPRAVIT:", flush=True)
        for name, _, detail in fails:
            print(f"    - {name}: {detail}", flush=True)
    if warns:
        print("\n  Na co si dát pozor (nebrání to běhu):", flush=True)
        for name, _, detail in warns:
            print(f"    - {name}: {detail}", flush=True)

    if not fails:
        print("\n  Vše podstatné funguje -- newsletter by měl projít.", flush=True)

    # Diagnostika záměrně nikdy nekončí chybou, aby se log vždy zobrazil celý.
    return 0


def main() -> int:
    print("DIAGNOSTIKA AGENTA SLÁVA/VOLKLORE", flush=True)
    print(f"Čas: {datetime.now(timezone.utc).isoformat()}", flush=True)

    try:
        sources = load_sources()
        settings = load_settings()
    except Exception as e:  # noqa: BLE001
        print(f"CHYBA: nepodařilo se načíst konfiguraci: {e}", flush=True)
        traceback.print_exc()
        return 0

    for step in (
        lambda: check_secrets(),
        lambda: check_openai(settings),
        lambda: check_supabase(),
        lambda: check_resend(settings),
        lambda: check_supadata(sources),
        lambda: check_jina(),
        lambda: check_sources(sources, settings),
    ):
        try:
            step()
        except Exception as e:  # noqa: BLE001
            print(f"[CHYBA] Test spadl neočekávaně: {e}", flush=True)
            traceback.print_exc()

    return summary()


if __name__ == "__main__":
    sys.exit(main())
