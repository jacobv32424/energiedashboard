"""Client voor de slimmemeterportal.nl UserAPI -- echte historische
kwartierdata (elektriciteit + gas), gebruikt om de periode vóór het begin
van de eigen P1-logging (2 juli 2026) met echte data te vullen i.p.v. een
schatting. Resultaten worden lokaal gecachet (config.SLIMMEMETERPORTAL_HISTORIE_PAD)
-- dit dashboard raadpleegt de externe API dus nooit live bij een paginalaad,
alleen de (eenmalige/periodieke) backfill doet dat."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

import config

_BASIS_URL = "https://app.slimmemeterportal.nl/userapi/v1"


def _get(pad: str) -> dict | list:
    verzoek = urllib.request.Request(
        f"{_BASIS_URL}{pad}",
        headers={"API-Key": config.SLIMMEMETERPORTAL_API_KEY},
    )
    with urllib.request.urlopen(verzoek, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def connecties_ophalen() -> list[dict]:
    """[{'meter_identifier', 'connection_type' ('elektriciteit'/'gas'),
    'start_date', 'end_date'}, ...]."""
    return _get("/connections")


def _kommagetal(waarde) -> float:
    if waarde in (None, "-", ""):
        return 0.0
    return float(str(waarde).replace(".", "").replace(",", "."))


def dagverbruik_ophalen(connection_id: str, dag: date) -> dict:
    """Som van import/export voor één dag, uit de API-intervallen.
    Elektriciteit: kwartierintervallen met delivery_low/high +
    returned_delivery_low/high (kWh). Gas: uurintervallen met alleen
    delivery (m3), geen teruglevering -- ander schema, dezelfde functie
    dekt beide af."""
    data = _get(f"/connections/{connection_id}/usage/{dag.strftime('%d-%m-%Y')}")
    import_totaal = export_totaal = 0.0
    for u in data.get("usages", []):
        if "delivery_low" in u or "delivery_high" in u:
            import_totaal += _kommagetal(u.get("delivery_low")) + _kommagetal(u.get("delivery_high"))
            export_totaal += _kommagetal(u.get("returned_delivery_low")) + _kommagetal(u.get("returned_delivery_high"))
        else:
            import_totaal += _kommagetal(u.get("delivery"))
    return {"import": round(import_totaal, 3), "export": round(export_totaal, 3)}


def historie_lezen() -> dict:
    """Lokale cache: {'elektriciteit': {'YYYY-MM-DD': {'import':.., 'export':..}},
    'gas': {'YYYY-MM-DD': {'import':.., 'export':..}}}."""
    if not os.path.exists(config.SLIMMEMETERPORTAL_HISTORIE_PAD):
        return {"elektriciteit": {}, "gas": {}}
    with open(config.SLIMMEMETERPORTAL_HISTORIE_PAD, "r", encoding="utf-8") as f:
        return json.load(f)


def _historie_opslaan(historie: dict) -> None:
    os.makedirs(os.path.dirname(config.SLIMMEMETERPORTAL_HISTORIE_PAD), exist_ok=True)
    with open(config.SLIMMEMETERPORTAL_HISTORIE_PAD, "w", encoding="utf-8") as f:
        json.dump(historie, f, ensure_ascii=False, indent=2)


def backfill(vanaf: date, tot: date, log=print) -> dict:
    """Haalt voor elke connectie (elektriciteit + gas) het dagverbruik op
    voor [vanaf, tot] en zet het in de lokale cache. Respecteert de
    rate limit van de API (60 verzoeken/minuut) met een kleine pauze
    tussen aanroepen. Overschrijft bestaande dagen in de cache (opnieuw
    draaien voor een al gecachete periode is dus onschadelijk)."""
    connecties = connecties_ophalen()
    historie = historie_lezen()

    for c in connecties:
        soort = c["connection_type"]
        if soort not in historie:
            historie[soort] = {}
        dag = vanaf
        while dag <= tot:
            sleutel = dag.isoformat()
            for poging in range(3):
                try:
                    historie[soort][sleutel] = dagverbruik_ophalen(c["meter_identifier"], dag)
                    break
                except urllib.error.HTTPError as e:
                    if e.code == 429:
                        wacht = int(e.headers.get("Retry-After", "30"))
                        log(f"  rate limit geraakt, wacht {wacht}s...")
                        time.sleep(wacht)
                        continue
                    log(f"  fout bij {soort} {sleutel}: {e}")
                    break
            log(f"{soort} {sleutel}: {historie[soort].get(sleutel)}")
            dag += timedelta(days=1)
            time.sleep(1.1)  # ruim onder de 60/minuut-limiet

    _historie_opslaan(historie)
    return historie
