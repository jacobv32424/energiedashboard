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

**Bevestigd door Vandebron (2026-07-28):** energiebelasting komt bovenop
de Levering-tarieven (dus `ELEKTRICITEIT_NORMAAL_KWH` = € 0,14632 +
energiebelasting € 0,11085 = € 0,25717 werkelijk normaaltarief) -- de
code rekende dit al goed, geen wijziging nodig.

**Open punt (nieuw):** Vandebron noemt ook een aparte "inkoopvergoeding"
bovenop levering + energiebelasting + btw, die nergens in
`geschatte_rekening()` is meegenomen -- ontbrekend tarief, navragen bij
Jacob (staat mogelijk ook op het contractoverzicht, net als de andere
componenten).

Draait op de Pi als `energiedashboard.service`, poort 8421, als user
`jacob` (zelfde patroon als `adressenboek.service`). Database staat op de
PortableSSD, niet op de SD-kaart (schrijfcycli) — pad via de
omgevingsvariabele `ENERGIEDASHBOARD_DB_PAD` in
`/etc/energiedashboard/env` (of direct in de systemd-unit).

`dev_data/energie.db` is een lokale ontwikkelkopie (via `scp` van de Pi) om
zonder SSH te kunnen testen — nooit de bron van waarheid, en niet
meenemen in de rsync-deploy naar de Pi.

Geen geformaliseerde testsuite: verifieer wijzigingen door de app lokaal
te draaien tegen `dev_data/energie.db` (zie de `run`-skill) en een
screenshot te maken (licht + donker thema, alle vier periodes: dag/week/
maand/jaar), niet alleen op afwezigheid van foutmeldingen vertrouwen.

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
