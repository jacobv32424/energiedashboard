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
