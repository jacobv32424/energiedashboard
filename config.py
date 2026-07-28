import os

# Pad naar de energie-database. Op de Pi zet de systemd-service dit via de
# omgevingsvariabele naar de echte locatie op de PortableSSD; lokaal (dev)
# valt dit terug op de meegeleverde ontwikkelkopie.
DB_PATH = os.environ.get(
    "ENERGIEDASHBOARD_DB_PAD",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "dev_data", "energie.db"),
)

# Tarieven normaal/dal, all-in incl. btw -- overgenomen uit
# energieproject/config.py op de Pi (Vandebron-contract). Dit dashboard is
# een apart project van de logger-service en raakt die code niet aan (zie
# CLAUDE.md) -- bij een tariefwijziging dus op BEIDE plekken bijwerken.
VAST_TARIEF_NORMAAL_KWH = 0.14632
VAST_TARIEF_DAL_KWH = 0.12081
VAST_TERUGLEVER_NORMAAL_KWH = 0.14632
VAST_TERUGLEVER_DAL_KWH = 0.12081
