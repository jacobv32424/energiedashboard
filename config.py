import os

# Pad naar de energie-database. Op de Pi zet de systemd-service dit via de
# omgevingsvariabele naar de echte locatie op de PortableSSD; lokaal (dev)
# valt dit terug op de meegeleverde ontwikkelkopie.
DB_PATH = os.environ.get(
    "ENERGIEDASHBOARD_DB_PAD",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "dev_data", "energie.db"),
)

# Pad naar het voorschotten-bestand -- puur eigen invoer van Jacob (geen
# afgeleide meetdata), dus geen plek in de (read-only) logger-database.
# Zelfde dev/prod-scheiding als DB_PATH hierboven.
VOORSCHOT_PAD = os.environ.get(
    "ENERGIEDASHBOARD_VOORSCHOT_PAD",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "dev_data", "voorschotten.json"),
)

# slimmemeterportal.nl UserAPI -- echte historische kwartierdata (elektriciteit
# + gas, terug tot 2015), gebruikt om de periode vóór het begin van de eigen
# P1-logging (2 juli 2026) met echte data te vullen i.p.v. een schatting.
# De sleutel komt bij voorkeur uit een omgevingsvariabele; lokaal (dev) valt
# dit terug op een bestand in dev_data/ (buiten git, zie .gitignore) zodat
# de sleutel nooit in de repository terechtkomt.
SLIMMEMETERPORTAL_API_KEY = os.environ.get("SLIMMEMETERPORTAL_API_KEY", "")
if not SLIMMEMETERPORTAL_API_KEY:
    _sleutel_pad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dev_data", "slimmemeterportal_api_key.txt")
    if os.path.exists(_sleutel_pad):
        with open(_sleutel_pad, "r", encoding="utf-8") as f:
            SLIMMEMETERPORTAL_API_KEY = f.read().strip()

SLIMMEMETERPORTAL_HISTORIE_PAD = os.environ.get(
    "ENERGIEDASHBOARD_HISTORIE_PAD",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "dev_data", "historie_slimmemeter.json"),
)

# Alle bedragen hieronder komen letterlijk van het GroenChoice-contractoverzicht
# van Jacob en van rechtstreekse navraag bij GroenChoice (2026-07-28),
# "inclusief btw". Dit dashboard is een apart project van de logger-service
# en raakt die code niet aan (zie CLAUDE.md) -- bij een tariefwijziging dus
# hier bijwerken (niet in energieproject/config.py).
#
# Bevestigd door GroenChoice: energiebelasting komt BOVENOP de kWh-tarieven
# hieronder (dus niet al inbegrepen), en er is daarnaast nog een
# "inkoopvergoeding" per kWh/m3 (voor dynamische contracten -- Jacob heeft
# een dynamisch contract, vandaar dat dit dashboard uberhaupt bestaat).
#
# Contract loopt tot 1 mei 2027 -- tarieven hieronder zijn tot die datum
# geldig, daarna controleren/bijwerken.

# --- Elektriciteit: levering -------------------------------------------------
ELEKTRICITEIT_NORMAAL_KWH = 0.14632
ELEKTRICITEIT_DAL_KWH = 0.12081

# Teruglevering onder de salderingsregeling (zelfde tarief als levering,
# terugbetaald) -- geldt tot het punt waar je op jaarbasis meer teruglevert
# dan je verbruikt; daarboven geldt de lagere terugleververgoeding. Dit
# dashboard rekent voorlopig met volledige saldering (eenvoudiger, en over
# een paar weken data kan de jaargrens toch niet betrouwbaar bepaald worden).
ELEKTRICITEIT_SALDERING_NORMAAL_KWH = 0.14632
ELEKTRICITEIT_SALDERING_DAL_KWH = 0.12081
ELEKTRICITEIT_TERUGLEVERVERGOEDING_STANDAARD_KWH = 0.14000  # boven de salderingsgrens (nog niet toegepast)
ELEKTRICITEIT_TERUGLEVERVERGOEDING_VERLAAGD_KWH = 0.07000   # idem, verlaagd tarief

# Inkoopvergoeding (dynamisch contract): geldt per verbruikte EN per
# teruggeleverde kWh (geen onderscheid normaal/dal). Bij teruglevering wordt
# dit -- net als de vaste terugleveringskosten hierboven -- op de
# jaarafrekening gecorrigeerd zodra je over het jaar meer teruglevert dan je
# verbruikt; dit dashboard rekent voorlopig zonder die correctie.
ELEKTRICITEIT_INKOOPVERGOEDING_KWH = 0.02571

# --- Elektriciteit: vaste kosten ---------------------------------------------
ELEKTRICITEIT_VASTE_LEVERINGSKOSTEN_PER_DAG = 0.19713
ELEKTRICITEIT_NETBEHEERKOSTEN_PER_DAG = 1.30970
ELEKTRICITEIT_VERMINDERING_ENERGIEBELASTING_PER_DAG = 1.72199  # korting, dus dit bedrag wordt afgetrokken

# Vaste terugleveringskosten: schaal o.b.v. je totale teruglevering per JAAR
# (niet per dag ondanks de eenheid "dag" op de factuur -- het is een vaste
# dagprijs die per schaal verschilt). Met maar een paar weken (zomer)data is
# een jaarschatting onbetrouwbaar (te veel zon-bias) -- schaal hieronder is
# een voorlopige inschatting, aanpasbaar zodra er een heel jaar aan data is.
ELEKTRICITEIT_VASTE_TERUGLEVERINGSKOSTEN_SCHALEN = [
    (0, 5, 0.00000),
    (5, 1000, 0.13142),
    (1000, 2000, 0.41068),
    (2000, 3000, 0.68994),
    (3000, 4000, 0.95277),
    (4000, 5000, 1.23203),
    (5000, float("inf"), 1.51129),
]

# --- Elektriciteit: energiebelasting (schijven, per jaar-kWh) ----------------
ELEKTRICITEIT_ENERGIEBELASTING_SCHALEN = [
    (0, 2900, 0.11085),
    (2900, 10_000, 0.11085),
    (10_000, 50_000, 0.08072),
    (50_000, 10_000_000, 0.04519),
    (10_000_000, float("inf"), 0.00375),
]

# --- Gas ----------------------------------------------------------------
GAS_LEVERING_M3 = 0.47081
GAS_REGIOTOESLAG_M3 = 0.03447
GAS_LOKAAL_INVESTEREN_M3 = 0.00572
GAS_ENERGIEBELASTING_SCHALEN = [
    (0, 1_000, 0.72680),
    (1_000, 170_000, 0.72680),
    (170_000, 1_000_000, 0.40033),
    (1_000_000, 10_000_000, 0.25889),
    (10_000_000, float("inf"), 0.06429),
]
GAS_VASTE_LEVERINGSKOSTEN_PER_DAG = 0.19713
GAS_NETBEHEERKOSTEN_PER_DAG = 0.73048
GAS_INKOOPVERGOEDING_M3 = 0.05983

# Gasverbruik wordt pas sinds 2026-07-28 gelogd (energy_logger.py loggede dit
# aanvankelijk niet, ook al geeft de P1-meter het door) -- voor data van
# vóór die datum is er dus geen gasstand beschikbaar.
