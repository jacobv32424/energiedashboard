import os

# Pad naar de energie-database. Op de Pi zet de systemd-service dit via de
# omgevingsvariabele naar de echte locatie op de PortableSSD; lokaal (dev)
# valt dit terug op de meegeleverde ontwikkelkopie.
DB_PATH = os.environ.get(
    "ENERGIEDASHBOARD_DB_PAD",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "dev_data", "energie.db"),
)

# Alle bedragen hieronder komen letterlijk van het Vandebron-contractoverzicht
# van Jacob (2026-07-28), "inclusief btw". Dit dashboard is een apart project
# van de logger-service en raakt die code niet aan (zie CLAUDE.md) -- bij een
# tariefwijziging dus hier bijwerken (niet in energieproject/config.py).
#
# LET OP -- nog niet 100% opgehelderd: Jacob zei eerder dat energiebelasting
# al in de kWh-tarieven hieronder zit, maar het contractoverzicht toont
# Energiebelasting als aparte regel onder "Overheidsheffingen". Deze
# instellingen gaan uit van het contractoverzicht (dus energiebelasting
# TELT APART mee) -- als dat niet klopt, ELEKTRICITEIT_ENERGIEBELASTING_KWH
# hieronder op 0 zetten.

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

# Gasverbruik wordt pas sinds 2026-07-28 gelogd (energy_logger.py loggede dit
# aanvankelijk niet, ook al geeft de P1-meter het door) -- voor data van
# vóór die datum is er dus geen gasstand beschikbaar.
