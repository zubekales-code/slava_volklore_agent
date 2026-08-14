# AI agent Sláva / Volklore — newsletter

Automatický denní (6 min) a týdenní (delší) přehled fashion/design/marketing/
tech/Czech-CEE scény pro Vic. Běží zdarma na GitHubu, jediná placená položka
je OpenAI API (řádově jednotky dolarů měsíčně).

Tenhle README je psaný pro člověka, který nekóduje — postupuj krok za krokem.

---

## 1. Co je potřeba založit (účty)

Vše kromě OpenAI je zdarma pro tenhle rozsah použití.

| Služba | K čemu | Odkaz |
|---|---|---|
| OpenAI API | psaní a třídění newsletteru | máš už založeno |
| GitHub | hostování kódu + spouštění | github.com |
| Supabase | databáze / deduplikace | supabase.com |
| Resend | odeslání e-mailu | resend.com |
| Supadata | přepisy YouTube videí | supadata.ai |
| Jina AI | (nepovinné) vyšší rychlostní limit pro čtení webů | jina.ai |

### 1.1 OpenAI
V [platform.openai.com](https://platform.openai.com) v sekci **API keys**
vytvoř nový klíč. Zkopíruj si ho (zobrazí se jen jednou) — bude potřeba
v kroku 3.

### 1.2 GitHub
Založ si účet, pokud ho ještě nemáš. Repozitář s kódem ti buď pošlu, nebo
si ho založíš podle pokynů níže (krok 2).

### 1.3 Supabase
1. Založ nový projekt (zdarma tier stačí).
2. V levém menu **SQL Editor** → **New query** → vlož obsah souboru
   `sql/schema.sql` z tohoto repozitáře → **Run**. Vytvoří se tabulka
   `items`, do které se bude vše ukládat.
3. V **Project Settings → API** najdeš:
   - **Project URL** → to je `SUPABASE_URL`
   - **service_role key** (ne "anon" klíč!) → to je `SUPABASE_KEY`

### 1.4 Resend
1. Založ účet, ověř e-mail.
2. V **API Keys** vytvoř nový klíč → to je `RESEND_API_KEY`.
3. Pro rozjezd stačí odesílat z testovací adresy `onboarding@resend.dev`
   (už nastaveno v `config/settings.yaml`). Pokud budeš později chtít
   odesílat z vlastní domény (např. `agent@slavavolklore.com`), Resend tě
   provede ověřením domény (přidání pár DNS záznamů) — dej vědět, pomůžu.

### 1.5 Supadata
Založ účet na supadata.ai, v nastavení najdeš API klíč → `SUPADATA_API_KEY`.
Zdarma tier: 100 přepisů/měsíc, na 2 kanály v rozsahu tohoto projektu
bohatě stačí.

### 1.6 Jina AI (nepovinné)
Funguje i bez klíče (jen s nižším rychlostním limitem, který ale pro
denní běh stačí). Klíč zakládej, jen kdybychom v budoucnu narazili na limit.

---

## 2. Nahrání kódu na GitHub

Pokud ti kód pošlu jako soubor/zip:

1. Na github.com klikni **New repository**. Nastav ho jako **Private**
   (obsahuje sice jen kód, ne klíče, ale soukromé je bezpečnější).
2. V novém prázdném repozitáři použij tlačítko **uploading an existing
   file** a nahraj tam obsah složky (přetažením myší jde nahrát rovnou
   celá struktura složek).
3. Commitni (uloží se to tlačítkem **Commit changes**).

---

## 3. Nastavení klíčů (GitHub Secrets)

Klíče z kroku 1 se **nikdy** nedávají přímo do kódu ani do souborů
v repozitáři — GitHub na to má speciální bezpečné úložiště.

V repozitáři: **Settings → Secrets and variables → Actions → New
repository secret**. Přidej postupně těchto 5 (jméno musí být přesně
takhle, hodnotu vlož svoji):

- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `RESEND_API_KEY`
- `SUPADATA_API_KEY`

(Volitelně i `JINA_API_KEY`, pokud ho budeš zakládat.)

---

## 4. Vyzkoušení

V repozitáři na GitHubu: záložka **Actions** → vlevo klikni na
**„Sláva/Volklore Newsletter"** → tlačítko **„Run workflow"** vpravo →
vyber `daily` → **Run workflow**.

Za pár desítek sekund až pár minut by měl přijít e-mail na
`slavavolkloreagent@gmail.com`. Průběh (a případné chyby u jednotlivých
zdrojů — to je normální a očekávané, viz níže) uvidíš v logu daného běhu.

**Tohle samé tlačítko je tvoje „run once" funkce** — kdykoli budeš chtít
shrnutí mimo pravidelný čas, stačí přijít sem a spustit ručně (denní i
týdenní verzi).

---

## 5. Automatický provoz

Jakmile krok 4 projde, nic dalšího dělat nemusíš — GitHub bude spouštět
agenta sám:

- **denně v 8:00** (krátká verze, ~6 minut čtení)
- **v neděli navíc** i **delší týdenní shrnutí**

### Dvakrát ročně: přepnutí letního/zimního času

GitHub umí plánovat běhy jen podle světového času (UTC), ne podle
pražského. Aby newsletter chodil v 8:00 pražského času celoročně, je
potřeba dvakrát ročně (při přechodu na letní/zimní čas) upravit soubor
`.github/workflows/newsletter.yml`:

- **konec března** (přechod na letní čas): oba řádky `cron:` nastav na
  `'0 6 * * *'` a `'0 6 * * 0'`
- **konec října** (přechod na zimní čas): oba řádky `cron:` nastav na
  `'0 7 * * *'` a `'0 7 * * 0'`

Stačí otevřít soubor na GitHubu, kliknout na tužku, přepsat `6` na `7`
(nebo naopak) na obou řádcích s `cron:`, a uložit. Do budoucna se tohle
dá i zautomatizovat, ale pro start to takhle stačí.

---

## 6. Jak upravovat nastavení (bez programování)

Všechno, co budeš chtít měnit, je v těchto souborech — otevřeš je na
GitHubu, klikneš na ikonu tužky, upravíš text, uložíš (**Commit
changes**). Příští běh se řídí novou verzí automaticky.

- **`config/sources.yaml`** — seznam zdrojů (weby, YouTube kanály).
  Přidávání/mazání zdrojů, oprava nefunkční RSS adresy.
- **`config/settings.yaml`** — čas odeslání, e-mailová adresa, kolik
  položek se vybírá, jaké modely se používají.
- **`config/prompts/daily_writer.md`** a **`weekly_writer.md`** — přesně
  to, jak má agent psát (tón, struktura, délka).
- **`config/prompts/classifier.md`** — podle čeho agent posuzuje, co je
  relevantní.

---

## 7. Co dělat, když něco nejde

- **Zdroj se nenačítá** — normální a očekávané chování je, že se tiše
  přeskočí (viz zadání: "co nešlo, ignorovat"). V logu běhu (Actions →
  konkrétní běh → rozklikni krok "Spuštění agenta") uvidíš řádek
  `WARNING` s názvem zdroje a důvodem. Nic se tím nerozbije.
- **Nepřišel e-mail vůbec** — zkontroluj v logu, jestli běh proběhl celý
  (poslední řádek by měl být "Hotovo."), a jestli sekce "Odeslání e-mailu
  selhalo" neobsahuje chybu (nejčastěji špatně zkopírovaný `RESEND_API_KEY`).
- **Chci vidět, co se reálně nasbíralo** — v Supabase, záložka **Table
  Editor → items**, uvidíš syrová data ze všech běhů.

---

## 8. Struktura projektu (pro info, nemusíš se tím zabývat)

```
config/
  sources.yaml       <- zdroje (uprav klidně sama/sám)
  settings.yaml       <- nastavení (uprav klidně sama/sám)
  prompts/             <- instrukce pro AI agenta (uprav klidně sama/sám)
src/                    <- samotný kód (sem prosím nezasahovat bez konzultace)
sql/schema.sql          <- příkaz pro založení databázové tabulky
.github/workflows/       <- nastavení automatického spouštění
```
