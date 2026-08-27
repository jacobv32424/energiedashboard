# Werkinstructies voor Claude Code

## Autonome uitvoering

Zodra de scope van een taak duidelijk is, hoef je niet telkens opnieuw te
vragen of je door mag gaan — bugs oplossen, kleine verbeteringen, en
bijwerken op de Pi via `deploy/bijwerken-op-pi.sh` mogen direct, na lokale
controle. Blijf wel kort melden wát je doet en waarom.

**Grens die hier niet voor wijkt:** geld/financiële handelingen, iets
versturen namens Jacob, en echt destructieve operaties vragen altijd
expliciete toestemming per keer.

## Dit project

Klein, alleen-lezen Flask-dashboard voor de energieproject-data (P1-meter,
zonnepanelen, gas, dynamisch EPEX-tarief) die `energy_logger.py`/
`price_fetcher.py` op de Pi (`plex`, los project op
`/home/jacob/energieproject`) in SQLite loggen. Dit dashboard raakt die
logger-code normaliter **niet** aan — het leest er alleen uit; de enige
uitzondering was de toevoeging van gaslogging op 2026-07-28 (de P1-meter
gaf gasstanden door die de logger nog niet opsloeg — zie `metingen.gas_m3`,
sindsdien gelogd, met terugwerkende kracht niet beschikbaar). `config.py`
dupliceert bewust alle tarieven (elektriciteit + gas) uit het
Vandebron-contract: bij een tariefwijziging dus hier bijwerken, niet in
`energieproject/config.py`.

**Btw/energiebelasting/inkoopvergoeding -- uitgezocht met Vandebron
(2026-07-28), samengevat:**
- Het kale leveringstarief (`ELEKTRICITEIT_NORMAAL_KWH`/`_DAL_KWH`,
  van het contractoverzicht) is exclusief energiebelasting, inkoopvergoeding
  én btw -- die drie komen er nog bij, en btw wordt berekend over de som
  van alle drie (kale tarief + inkoopvergoeding + energiebelasting), niet
  los per component.
- De EPEX-dynamische prijs (`prijzen.prijs_kwh`, via
  `price_fetcher.py`/energyzero-bibliotheek met `PriceType.ALL_IN`) is
  ZELF al all-in: kale marktprijs + energiebelasting + btw zitten daar al
  in verwerkt (bevestigd door de waarden zelf: €0,29-0,37/kWh, veel te
  hoog voor een kale groothandelsprijs). Alleen de Vandebron-specifieke
  inkoopvergoeding (leveranciersopslag, geen marktgegeven, dus nooit in
  een generieke marktprijs-bibliotheek verwerkt) ontbreekt daar en wordt
  apart opgeteld, inclusief de 21% btw daarover.
- `kosten_vergelijking()` (vast vs. dynamisch) gebruikt daarom voor de
  "vast"-kant: (kale tarief + energiebelasting) x 1,21 -- geen
  inkoopvergoeding, want die geldt specifiek voor dynamische contracten.
  `geschatte_rekening()` gebruikt de EPEX-prijs voor de energiekosten
  (al all-in) plus apart de inkoopvergoeding x 1,21.
- Energiebelasting-schijf: voor de "vast"-vergelijking wordt steeds de
  eerste schijf (`ELEKTRICITEIT_ENERGIEBELASTING_SCHALEN[0]`) gebruikt als
  vereenvoudiging -- ruim voldoende gezien de volumes.
- Contract loopt tot 1 mei 2027 -- tarieven tot die datum geldig.

Draait op de Pi als `energiedashboard.service`, poort 8421, als user
`jacob` (zelfde patroon als `adressenboek.service`). Database staat op de
PortableSSD, niet op de SD-kaart (schrijfcycli) — pad via de
omgevingsvariabele `ENERGIEDASHBOARD_DB_PAD` in
`/etc/energiedashboard/env` (of direct in de systemd-unit).

`dev_data/energie.db` is een lokale ontwikkelkopie (via `scp` van de Pi) om
zonder SSH te kunnen testen — nooit de bron van waarheid, en niet
meenemen in de rsync-deploy naar de Pi.

## Voorschot -- eigen opslag, geen meetdata

Het voorschotbedrag (Instellingen op het dashboard zelf, per maand
wijzigbaar) is Jacobs eigen invoer, geen afgeleide meetdata -- staat dus
niet in de (read-only) logger-database maar in een eigen JSON-bestand,
pad via `config.VOORSCHOT_PAD` (env var `ENERGIEDASHBOARD_VOORSCHOT_PAD`,
dev-fallback `dev_data/voorschotten.json`). Zie `dataset.py`:
`voorschotten_lezen()`/`voorschot_toevoegen()`/`voorschot_voor_periode()`.

## slimmemeterportal.nl -- echte historische data i.p.v. simulatie

De eigen P1-logging begint pas 2 juli 2026. Voor een zelfgekozen
rekening-startdatum daarvóór (`geschatte_rekening(kosten, vanaf=...)` in
`dataset.py`) wordt niet blind gesimuleerd: `slimmemeterportal.py` haalt
via de UserAPI van slimmemeterportal.nl (Jacobs eigen PlusAccount, data
sinds 2015) echte kwartier-/uurdata op voor elektriciteit én gas.

- Auth: header `API-Key`. Endpoints: `GET /userapi/v1/connections` (lijst
  met `meter_identifier`/`connection_type`), `GET
  /userapi/v1/connections/{id}/usage/{dd-mm-YYYY}` (per-interval
  `delivery_low`/`delivery_high`/`returned_delivery_low`/`_high` voor
  elektriciteit, alleen `delivery` voor gas -- Nederlandse komma-
  decimalen, zie `slimmemeterportal._kommagetal()`).
- **Sleutel nooit in git**: `config.SLIMMEMETERPORTAL_API_KEY` komt uit de
  omgevingsvariabele `SLIMMEMETERPORTAL_API_KEY`, met lokale dev-fallback
  `dev_data/slimmemeterportal_api_key.txt` (buiten git, zie
  `.gitignore` -- `dev_data/` staat daar al in). Op de Pi hoort de
  sleutel in de systemd-env, net als `ENERGIEDASHBOARD_DB_PAD`.
  **Nooit** hardcoden in een bestand dat getrackt wordt.
- **Geen live API-aanroepen tijdens een paginalaad** (rate limit 60/min,
  en dit dashboard moet snel blijven): `slimmemeterportal.backfill(vanaf,
  tot)` haalt eenmalig (of periodiek, handmatig opnieuw te draaien) data
  op en schrijft die naar een lokale cache
  (`config.SLIMMEMETERPORTAL_HISTORIE_PAD`, env var
  `ENERGIEDASHBOARD_HISTORIE_PAD`, dev-fallback
  `dev_data/historie_slimmemeter.json`). `dataset.py` leest alleen uit
  die cache; ontbreekt een dag daarin, dan valt de berekening terug op
  het gemiddeld-dagprofiel (de oorspronkelijke schatting).
- Nieuwe periode nodig (bijv. weer een gat verder terug)? Draai
  `slimmemeterportal.backfill(date(...), date(...))` opnieuw (overschrijft
  bestaande cache-dagen, dus onschadelijk om te herhalen) en, voor de
  bijbehorende EPEX-prijzen, `~/energieproject/backfill_prijzen.py` op de
  Pi (zie hieronder) voor dezelfde periode.

## EPEX-prijzen backfillen (eenmalig/incidenteel, raakt de Pi)

`~/energieproject/backfill_prijzen.py` (op de Pi, hergebruikt
`price_fetcher.py`'s `haal_prijzen_op()`/`init_db()`) vult de
`prijzen`-tabel met historische EPEX-dagprijzen voor een periode:
`python3 backfill_prijzen.py --vanaf YYYY-MM-DD --tot YYYY-MM-DD`. Dit is
de enige uitzondering op "dit dashboard raakt de logger-database niet
aan" (zie boven) -- puur aanvullend (INSERT OR REPLACE, geen bestaande
rijen worden gewijzigd), en altijd met Jacobs akkoord op het moment zelf
gedraaid, niet automatisch.

Geen geformaliseerde testsuite: verifieer wijzigingen door de app lokaal
te draaien tegen `dev_data/energie.db` (zie de `run`-skill) en een
screenshot te maken (licht + donker thema, alle vier periodes: dag/week/
maand/jaar), niet alleen op afwezigheid van foutmeldingen vertrouwen.

## Inhoudsopgave op de Handleiding-pagina (2026-08-10)

`/handleiding` (`app.py::handleiding()`) kreeg de `toc`-extensie van
python-markdown (`extensions=["tables", "toc"], extension_configs={"toc":
{"toc_depth": "2-3"}}`) en `templates/handleiding.html` een `.toc`-CSS-
blok (afgeronde kaart, `›`-pijltjes, ingesprongen sub-lijst) in dezelfde
Fraunces/IBM-Plex-stijl als de rest van de pagina — zelfde soort
behandeling als Filmproject/Filmsplitser/Dubbele Bestanden Opsporen
kregen (Jacob: "wel zou in nog een help? index willen hebben", verbreed
naar "alle programma", "alles mooi grafisch"). `Handleiding.md` kreeg een
`## Inhoud` + `[TOC]`-marker na de inleidende alinea. Getest via een
losse markdown-render + Jinja-render buiten de app, met een headless-
Chrome-screenshot ter controle.

## "Database is locked" gefixt (20-08-2026)

Ontdekt via Commandocentrums Pi-overzicht: het dashboard gaf een 500-fout
(`sqlite3.OperationalError: database is locked`) doordat `energy_logger.py`
op de Pi continu naar dezelfde `energie.db` schrijft terwijl dit dashboard
leest — zonder WAL-modus en zonder een sqlite3-timeout faalt zo'n botsing
meteen in plaats van even te wachten. Twee onderdelen, geen van beide raakt
de logger-code (blijft bij "dit dashboard leest alleen", zie hierboven):

- **`PRAGMA journal_mode=WAL`** eenmalig gezet op `energie.db` zelf (niet
  in code — een eigenschap van het databasebestand). Vóór deze wijziging
  is een backup gemaakt (`energie.db.backup-20260820`, op de Pi).
- **`sqlite3.connect(..., timeout=10)`** in `dataset._connect()` — het
  vangnet: bij een korte, resterende lock wordt nu even gewacht i.p.v.
  meteen gefaald.
- **`kosten_vergelijking()` kreeg een 5-minuten in-memory cache** — deze
  query leest de VOLLE `metingen`-tabel (69k+ rijen, groeit continu), wat
  op de externe SSD 10-20 sec kon duren. De cache verandert niets aan de
  uitkomst, alleen hoe vaak de zware query opnieuw draait.

**Vervolgstap, alsnog gedaan (20-08-2026, via Commandocentrums nachtelijke
Gezondheidscontrole)**: de Gezondheidscontrole signaleerde een paginalaad
van 15,9 sec. Uitgezocht met een losse profileerpoging op de Pi zelf
(elke `dataset`-functie apart getimed): niet de SQL-queries zelf (allemaal
sub-milliseconde dankzij `timestamp`/`kwartier_start` als PRIMARY KEY),
maar de Python-verwerking ná het ophalen van de volle `metingen`-tabel
(69k+ rijen) in twee functies: `kosten_vergelijking()` (al gecached sinds
de vorige fix hierboven, maar duurde ~8 sec bij een koude cache) en
`zonpatroon_per_uur()` (had nog HELEMAAL geen cache, ~6,6 sec bij élke
aanroep). Samen verklaarden die twee vrijwel de volledige 15,9 sec.
`huidige_stand()`/`zelfvoorzienendheid()`/`vermogen_serie()` bleken bij
het profileren juist al snel (< 0,1 sec) — geen van drieën leest de volle
tabel.

**Fix**: `zonpatroon_per_uur()` kreeg dezelfde 5-minuten in-memory cache
als `kosten_vergelijking()` (zelfde patroon: `_ZONPATROON_CACHE`-dict,
niets aan de uitkomst verandert, alleen hoe vaak de zware verwerking
opnieuw draait — dit patroon mag hierna, was het antwoord). Geverifieerd
op de Pi zelf: eerste laadbeurt na een herstart nog steeds ~16 sec (koude
cache, onvermijdelijk bij twee ongecachede full-table-verwerkingen),
tweede/derde laadbeurt binnen het cache-venster ~0,45 sec. Gedeployed via
`deploy/bijwerken-op-pi.sh`, service netjes herstart.

**Koude-cache-moment ook opgelost (20-08-2026, via Commandocentrums
Gezondheidscontrole)**: precies de hierboven genoemde achtergrond-
ververser, alsnog gebouwd nadat de Gezondheidscontrole dit drie keer
als "traag" (~15 sec) bleef melden. `app.py`: `_cache_ververser()`,
een daemon-thread (gestart in de `__main__`-guard) die elke 4 min —
korter dan de 5-minuten cache-geldigheid van `kosten_vergelijking()`/
`zonpatroon_per_uur()` — beide functies alvast aanroept. Een bezoeker
treft zo altijd de warme cache, ook de eerste na een herstart. Live
geverifieerd op de Pi: 20 sec na een herstart al 1,3 sec laadtijd
(was 15-16 sec), en drie vervolgmetingen consistent 0,5-0,7 sec. De
Gezondheidscontrole-tab bevestigt dit ook: van "🟡 traag" naar "🟢 ok"
(0,5 sec) in de eerstvolgende controle na de deploy.

## Documentatie bijhouden — twee plekken, niet één

Bij elke functionele wijziging (grafiek/KPI toegevoegd of verwijderd, doel
van een paneel veranderd) in dezelfde beurt bijwerken, zonder dat erom
gevraagd wordt:

- De "Waarom dit dashboard er is"-sectie onderin `templates/dashboard.html`
  (intro + kenmerken-kaartjes) — de beschrijving in de app zelf.
- **`Handleiding.md`** — de losse gebruikershandleiding in de project-root.

Taal moet in beide voor een leek te begrijpen zijn: geen jargon als
"EPEX", "kWh-delta" of "cumulatief" zonder uitleg. Zelfde principe als bij
Filmproject (Toelichting.md/Handleiding.md) en Adressenboek
(HANDLEIDING.md) — zie ook de globale afspraak hierover in
`~/.claude/CLAUDE.md`.

## Zijbalk-menu + Introductie (24-08-2026)

Dit dashboard bestond tot vandaag uit twee losse HTML-bestanden zonder
gedeelde basis-template (`templates/dashboard.html`,
`templates/handleiding.html`, elk hun eigen `<head>`/kleurtokens). Er is
nu een linker-zijbalk-menu bijgekomen (patroon van Spil,
`~/projects/Spil/spil/templates/basis.html` + `static/stijl.css`) en een
nieuwe Introductiepagina (patroon van roladministratie-web/
Commandocentrum) — beide zonder een `{% extends %}`-refactor, puur via
`{% include %}`:

- **`templates/partials/zijbalk.html`** — het ene, gedeelde menu
  (Dashboard/Introductie/Handleiding), via `{% include %}` in
  `dashboard.html`, `handleiding.html` én `introductie.html` geplakt.
  Verwacht een `actieve_pagina`-variabele, gezet met `{% set %}` vlak
  vóór de include in elke pagina (Jinja's `include` werkt "with context"
  by default, dus dat is genoeg — geen routewijziging nodig voor de
  actieve-status-highlight). Kleuren: vaste donkere achtergrond
  (`#0F1E1C`, dezelfde hex als dit dashboard se eigen lichte-thema
  `--inkt`) zodat de balk in zowel licht als donker thema donker blijft
  — een `var()` die met het thema meeschakelt zou de balk in donkere
  modus juist lícht maken. Actieve link gebruikt gewoon `var(--accent)`,
  die al met het thema meeschakelt en in beide standen goed leesbaar is.
  De bestaande vaste, rechtsboven zwevende "📖 Handleiding"-link in
  `dashboard.html` is **verwijderd** (incl. de bijbehorende
  `.handleiding-link`-CSS) — die werd dubbelop met de nieuwe zijbalk.
  De bestaande `.navigator`-periodetabs (dag/week/maand/jaar) zijn
  **niet** aangeraakt, dat blijft functionele periodenavigatie, geen
  sitenavigatie.
- **`templates/introductie.html`** (route `introductie`, `/introductie`,
  nieuw 24-08-2026) — een korte, visuele rondleiding: railnavigatie +
  voortgangsbalk, JS-gestuurd tonen/verbergen (geen paginaherlaad tussen
  stappen), zes hoofdstukken. **Alle links gebruiken `url_for(...)`**,
  geen kale `href`'s — een hernoemde/verwijderde route geeft dus een
  directe `BuildError` bij het opvragen van de pagina, geen stil kapotte
  link (zelfde vangnet als Spils versie van dit patroon).
  Stap-teksten zijn bewust groter en met meer regelafstand
  (`font-size:15.5px; line-height:1.8`) dan de rest van dit compactere
  dashboard — Jacob is dyslectisch/visueel ingesteld, expliciet op
  gelet bij deze pagina.

## Introductie & Handleiding: bijwerken is een discipline, geen automatisme

Zelfde afspraak als in Spils en roladministratie-web's CLAUDE.md: **er is
geen code die dit vanzelf doet.** Dit is een discipline die elke sessie
zelf moet toepassen, niet een mechanisme.

- **Handleiding.md** volgt de bestaande regel hierboven ("twee plekken,
  niet één"): bij elke functionele wijziging in dezelfde beurt
  bijwerken.
- **`templates/introductie.html`** is bewust kort en curated — zes
  hoofdstukken, het grote plaatje, geen naslagwerk. Niet elke kleine
  wijziging hoort hier thuis. Wél bijwerken bij: een nieuw item in de
  zijbalk (`templates/partials/zijbalk.html`); een nieuwe grafiek/KPI
  die het "grote plaatje" in stap 1/3 verandert; een wijziging aan de
  slimmemeterportal-koppeling of de rekening-logica (stap 3/4); of een
  hernoemde/verwijderde route die in de pagina gelinkt wordt.
- **Vangnet, maar niet compleet**: zie hierboven — alle links gebruiken
  `url_for(...)`, dus een hernoemde route breekt zichtbaar (`BuildError`),
  niet stil. De tekst zelf (uitleg, voorbeeldrijen) heeft dat vangnet
  niet en kan wél ongemerkt verouderen — daar blijft gerichte aandacht
  bij een grotere wijziging voor nodig.
- Geen nieuwe kleuren of lettertype toegevoegd voor deze twee
  onderdelen — alles hergebruikt de bestaande `--papier`/`--paneel`/
  `--inkt`/`--accent`/...-tokens en Fraunces/IBM Plex Sans die
  `dashboard.html`/`handleiding.html` al gebruikten.

## Patroon #1: Vragen, Wensen & Bevindingen (27-08-2026)

Geïmplementeerd (Commandocentrums patronen-overzicht, oorsprong Spil).
Eigen JSON-bestand `config.VRAGEN_PAD` (env var
`ENERGIEDASHBOARD_VRAGEN_PAD`, dev-fallback `dev_data/vragen.json`) --
zelfde eigen-invoer-redenering als `VOORSCHOT_PAD` hierboven (geen
meetdata, dus geen plek in de read-only logger-database). Functies in
`dataset.py` (`alle_vragen`/`vraag_toevoegen`/etc.), routes in `app.py`
(`/vragen`, `/vragen/toevoegen`, `/vragen/<id>/...`), nieuwe
`templates/vragen.html` (zelfde `.wrap`/`.paneel`-patroon als
`handleiding.html`, geen nieuwe kleuren/lettertype), nieuw zijbalk-item.

**Afwijking t.o.v. de Spil-referentie-implementatie**: geen "wie"-veld
(dit dashboard heeft geen gebruikersaccounts) en geen bijlagen-upload
(nog niet gevraagd). Geen versienummer in dit project --
`verwerkt_in_versie` gebruikt daarom een datumstempel.
