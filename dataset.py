"""Leest (alleen-lezen) uit de energie.db die energy_logger.py/price_fetcher.py
op de Pi vullen, en levert kant-en-klare series voor het dashboard."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import config
import slimmemeterportal as smp

LOCAL_TZ = ZoneInfo("Europe/Amsterdam")
_MAANDNAMEN = [
    "jan", "feb", "mrt", "apr", "mei", "jun",
    "jul", "aug", "sep", "okt", "nov", "dec",
]


def _connect():
    # timeout=10: zonder dit faalt een query meteen met "database is
    # locked" als energy_logger.py net op dat moment schrijft (SQLite's
    # standaard-timeout is 0 seconden) -- met een timeout wacht sqlite3
    # gewoon even tot de schrijver klaar is. Zie ook: journal_mode=WAL is
    # ingeschakeld op de database zelf (eenmalig via PRAGMA op de Pi,
    # 20-08-2026) -- de eigenlijke fix, dit is het vangnet.
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _naar_kwartier_utc(ts_iso: str) -> str:
    """Zelfde afronding als price_fetcher.py/simulator.py op de Pi, zodat
    metingen en prijzen op dezelfde kwartier-sleutel uitkomen."""
    dt = datetime.fromisoformat(ts_iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    kwartier_minuut = (dt_utc.minute // 15) * 15
    return dt_utc.replace(minute=kwartier_minuut, second=0, microsecond=0).isoformat()


def totaal_bespaard(kosten: list[dict]) -> dict | None:
    """Totaal bespaard/verloren door het dynamische tarief t.o.v. het vaste
    tarief, sinds het begin van de logging -- dit is de vergelijking die
    de HomeWizard-app zelf niet maakt (die kent alleen je eigen kWh-totalen,
    geen tariefvergelijking), dus hier zit de toegevoegde waarde."""
    if not kosten:
        return None
    eerste, laatste = kosten[0], kosten[-1]
    verschil = laatste["cumulatief_vast"] - laatste["cumulatief_dynamisch"]
    return {
        "sinds": datetime.strptime(eerste["dag"], "%Y-%m-%d").strftime("%d-%m-%Y"),
        "bedrag": round(abs(verschil), 2),
        "voordeliger": verschil >= 0,
    }


def zelfvoorzienendheid(vanaf: date | None = None) -> dict | None:
    """Indicatie van hoe zelfvoorzienend je bent: het aandeel van je totale
    verbruik dat overeenkomt met je teruglevering aan het net.

    Let op, dit is een ONDERGRENS, geen hard percentage: de P1-meter ziet
    alleen wat het net op/af gaat, niet je eigen directe verbruik van
    zelfopgewekte zonnestroom (die stroom passeert de meter nooit). Je
    daadwerkelijke zelfvoorzienendheid ligt dus altijd op zijn minst zo
    hoog als dit getal."""
    conn = _connect()
    if vanaf is not None:
        eerste = conn.execute(
            "SELECT * FROM metingen WHERE timestamp >= ? ORDER BY timestamp ASC LIMIT 1",
            (vanaf.isoformat(),),
        ).fetchone()
    else:
        eerste = conn.execute("SELECT * FROM metingen ORDER BY timestamp ASC LIMIT 1").fetchone()
    laatste = conn.execute("SELECT * FROM metingen ORDER BY timestamp DESC LIMIT 1").fetchone()
    conn.close()
    if eerste is None or laatste is None:
        return None

    import_totaal = max(0.0, laatste["energy_import_kwh"] - eerste["energy_import_kwh"])
    export_totaal = max(0.0, laatste["energy_export_kwh"] - eerste["energy_export_kwh"])
    verbruik_totaal = import_totaal + export_totaal
    if verbruik_totaal <= 0:
        return None

    return {
        "percentage": round(min(100.0, export_totaal / verbruik_totaal * 100), 1),
        "sinds": datetime.fromisoformat(eerste["timestamp"]).date().strftime("%d-%m-%Y"),
    }


def huidige_stand() -> dict | None:
    conn = _connect()
    laatste = conn.execute("SELECT * FROM metingen ORDER BY timestamp DESC LIMIT 1").fetchone()
    if laatste is None:
        conn.close()
        return None

    vandaag_start = datetime.now(timezone.utc).date().isoformat()
    eerste_vandaag = conn.execute(
        "SELECT * FROM metingen WHERE timestamp >= ? ORDER BY timestamp ASC LIMIT 1",
        (vandaag_start,),
    ).fetchone()
    huidige_prijs_rij = conn.execute(
        "SELECT prijs_kwh FROM prijzen WHERE kwartier_start <= ? ORDER BY kwartier_start DESC LIMIT 1",
        (datetime.now(timezone.utc).isoformat(),),
    ).fetchone()
    conn.close()

    verbruik_vandaag = teruglevering_vandaag = None
    if eerste_vandaag is not None:
        verbruik_vandaag = max(0.0, laatste["energy_import_kwh"] - eerste_vandaag["energy_import_kwh"])
        teruglevering_vandaag = max(0.0, laatste["energy_export_kwh"] - eerste_vandaag["energy_export_kwh"])

    return {
        "vermogen_w": laatste["power_w"],
        "tijdstip": laatste["timestamp"],
        "verbruik_vandaag_kwh": verbruik_vandaag,
        "teruglevering_vandaag_kwh": teruglevering_vandaag,
        "huidige_prijs_kwh": huidige_prijs_rij["prijs_kwh"] if huidige_prijs_rij else None,
    }


# --- Periode-navigatie (dag/week/maand/jaar) --------------------------------

_PERIODES = ("dag", "week", "maand", "jaar")
_BUCKET_PER_PERIODE = {"dag": "uur", "week": "dag", "maand": "dag", "jaar": "maand"}


def _periode_grenzen(periode: str, referentie: date) -> tuple[datetime, datetime]:
    """(start, eind) in UTC voor de gevraagde periode, o.b.v. lokale
    kalendergrenzen (Europe/Amsterdam) -- eind is exclusief."""
    if periode == "dag":
        start_lokaal = datetime(referentie.year, referentie.month, referentie.day, tzinfo=LOCAL_TZ)
        eind_lokaal = start_lokaal + timedelta(days=1)
    elif periode == "week":
        maandag = referentie - timedelta(days=referentie.weekday())
        start_lokaal = datetime(maandag.year, maandag.month, maandag.day, tzinfo=LOCAL_TZ)
        eind_lokaal = start_lokaal + timedelta(days=7)
    elif periode == "maand":
        start_lokaal = datetime(referentie.year, referentie.month, 1, tzinfo=LOCAL_TZ)
        if referentie.month == 12:
            eind_lokaal = datetime(referentie.year + 1, 1, 1, tzinfo=LOCAL_TZ)
        else:
            eind_lokaal = datetime(referentie.year, referentie.month + 1, 1, tzinfo=LOCAL_TZ)
    elif periode == "jaar":
        start_lokaal = datetime(referentie.year, 1, 1, tzinfo=LOCAL_TZ)
        eind_lokaal = datetime(referentie.year + 1, 1, 1, tzinfo=LOCAL_TZ)
    else:
        raise ValueError(f"onbekende periode: {periode}")
    return start_lokaal.astimezone(timezone.utc), eind_lokaal.astimezone(timezone.utc)


def periode_navigatie(periode: str, referentie: date) -> dict:
    """Labels + vorige/volgende-datums voor de periode-navigatiebalk."""
    start_utc, eind_utc = _periode_grenzen(periode, referentie)

    if periode == "dag":
        vorige, volgende = referentie - timedelta(days=1), referentie + timedelta(days=1)
        label = referentie.strftime("%d-%m-%Y")
    elif periode == "week":
        vorige, volgende = referentie - timedelta(days=7), referentie + timedelta(days=7)
        iso_jaar, iso_week, _ = referentie.isocalendar()
        label = f"Week {iso_week}, {iso_jaar}"
    elif periode == "maand":
        eerste_van_maand = referentie.replace(day=1)
        vorige = (eerste_van_maand - timedelta(days=1)).replace(day=1)
        volgende = (eerste_van_maand + timedelta(days=32)).replace(day=1)
        label = f"{_MAANDNAMEN[referentie.month - 1].capitalize()} {referentie.year}"
    elif periode == "jaar":
        vorige = referentie.replace(year=referentie.year - 1)
        volgende = referentie.replace(year=referentie.year + 1)
        label = str(referentie.year)
    else:
        raise ValueError(f"onbekende periode: {periode}")

    nu_utc = datetime.now(timezone.utc)
    return {
        "label": label,
        "vorige_datum": vorige.isoformat(),
        "volgende_datum": volgende.isoformat(),
        "kan_vooruit": eind_utc <= nu_utc,
    }


def _bucket_info(ts_iso: str, granulariteit: str) -> tuple[str, str]:
    """(sorteersleutel, weergavelabel) voor een timestamp, in lokale tijd."""
    dt = datetime.fromisoformat(ts_iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_lokaal = dt.astimezone(LOCAL_TZ)
    if granulariteit == "uur":
        return dt_lokaal.strftime("%Y-%m-%dT%H"), dt_lokaal.strftime("%H:00")
    if granulariteit == "dag":
        return dt_lokaal.strftime("%Y-%m-%d"), f"{dt_lokaal.day} {_MAANDNAMEN[dt_lokaal.month - 1]}"
    if granulariteit == "maand":
        return dt_lokaal.strftime("%Y-%m"), f"{_MAANDNAMEN[dt_lokaal.month - 1]} {dt_lokaal.year}"
    raise ValueError(granulariteit)


def vermogen_serie(periode: str, referentie: date) -> list[dict]:
    """Vermogen (W) over de gekozen periode. Alleen zinvol als lijn voor
    dag/week (bij maand/jaar wordt de instantane vermogenswaarde te ruizig
    en betekenisloos als lijn -- dan toont het dashboard alleen de
    verbruiksbalken)."""
    if periode not in ("dag", "week"):
        return []
    start_utc, eind_utc = _periode_grenzen(periode, referentie)
    conn = _connect()
    rijen = conn.execute(
        "SELECT timestamp, power_w FROM metingen WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp ASC",
        (start_utc.isoformat(), eind_utc.isoformat()),
    ).fetchall()
    conn.close()

    if periode == "dag":
        return [
            {"label": datetime.fromisoformat(r["timestamp"]).astimezone(LOCAL_TZ).strftime("%H:%M"), "vermogen_w": r["power_w"]}
            for r in rijen
        ]

    # week: uurgemiddelden, anders te veel punten (7 * 1440) voor een vlotte grafiek
    per_uur: dict[str, list[float]] = {}
    labels: dict[str, str] = {}
    for r in rijen:
        sleutel, label = _bucket_info(r["timestamp"], "uur")
        per_uur.setdefault(sleutel, []).append(r["power_w"])
        labels[sleutel] = label
    return [
        {"label": f"{sleutel[8:10]} {labels[sleutel]}", "vermogen_w": sum(w) / len(w)}
        for sleutel, w in sorted(per_uur.items())
    ]


def verbruik_per_periode(periode: str, referentie: date) -> list[dict]:
    """Import/teruglevering (kWh), gebucket op de granulariteit die bij de
    gekozen periode hoort (uur/dag/maand)."""
    start_utc, eind_utc = _periode_grenzen(periode, referentie)
    granulariteit = _BUCKET_PER_PERIODE[periode]

    conn = _connect()
    rijen = conn.execute(
        "SELECT timestamp, energy_import_kwh, energy_export_kwh FROM metingen "
        "WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp ASC",
        (start_utc.isoformat(), eind_utc.isoformat()),
    ).fetchall()
    conn.close()

    per_bucket: dict[str, dict] = {}
    labels: dict[str, str] = {}
    for r in rijen:
        sleutel, label = _bucket_info(r["timestamp"], granulariteit)
        labels[sleutel] = label
        if sleutel not in per_bucket:
            per_bucket[sleutel] = {"eerste_import": r["energy_import_kwh"], "eerste_export": r["energy_export_kwh"]}
        per_bucket[sleutel]["laatste_import"] = r["energy_import_kwh"]
        per_bucket[sleutel]["laatste_export"] = r["energy_export_kwh"]

    resultaat = []
    for sleutel in sorted(per_bucket):
        v = per_bucket[sleutel]
        resultaat.append({
            "label": labels[sleutel],
            "import_kwh": round(max(0.0, v["laatste_import"] - v["eerste_import"]), 3),
            "export_kwh": round(max(0.0, v["laatste_export"] - v["eerste_export"]), 3),
        })
    return resultaat


def gas_per_periode(periode: str, referentie: date) -> list[dict]:
    """Gasverbruik (m3), gebucket op dezelfde granulariteit als
    verbruik_per_periode(). Alleen import -- gas heeft geen teruglevering.
    Gas wordt pas sinds 28-07-2026 gelogd, dus oudere periodes tonen niets."""
    start_utc, eind_utc = _periode_grenzen(periode, referentie)
    granulariteit = _BUCKET_PER_PERIODE[periode]

    conn = _connect()
    rijen = conn.execute(
        "SELECT timestamp, gas_m3 FROM metingen "
        "WHERE timestamp >= ? AND timestamp < ? AND gas_m3 IS NOT NULL ORDER BY timestamp ASC",
        (start_utc.isoformat(), eind_utc.isoformat()),
    ).fetchall()
    conn.close()

    per_bucket: dict[str, dict] = {}
    labels: dict[str, str] = {}
    for r in rijen:
        sleutel, label = _bucket_info(r["timestamp"], granulariteit)
        labels[sleutel] = label
        if sleutel not in per_bucket:
            per_bucket[sleutel] = {"eerste": r["gas_m3"]}
        per_bucket[sleutel]["laatste"] = r["gas_m3"]

    resultaat = []
    for sleutel in sorted(per_bucket):
        v = per_bucket[sleutel]
        resultaat.append({
            "label": labels[sleutel],
            "gas_m3": round(max(0.0, v["laatste"] - v["eerste"]), 3),
        })
    return resultaat


_ZONPATROON_CACHE: dict = {"data": None, "opgehaald_op": 0.0}
_ZONPATROON_CACHE_SECONDEN = 300  # 5 min, zelfde patroon/duur als _KOSTEN_VERGELIJKING_CACHE


def zonpatroon_per_uur() -> list[dict]:
    """Gemiddelde teruglevering per uur van de dag, over alle beschikbare
    dagen -- laat zien wanneer de panelen typisch het meest opleveren,
    losstaand van welke specifieke dag je op dat moment bekijkt. Dit is
    het enige harde 'zonnegetal' dat uit P1-data valt te halen: de meter
    ziet alleen wat er het net op gaat, niet de rechtstreekse eigen
    consumptie van opgewekte stroom.

    5 minuten in-memory gecached (20-08-2026, zelfde reden/patroon als
    kosten_vergelijking(): leest ook de VOLLE metingen-tabel en kostte
    op de Pi zelf gemeten 6-7 seconden aan Python-verwerking per
    paginalaad, goed voor het merendeel van de traagheid die de
    nachtelijke Gezondheidscontrole signaleerde)."""
    nu = time.time()
    cache = _ZONPATROON_CACHE
    if cache["data"] is not None and nu - cache["opgehaald_op"] < _ZONPATROON_CACHE_SECONDEN:
        return cache["data"]

    conn = _connect()
    rijen = conn.execute(
        "SELECT timestamp, energy_export_kwh FROM metingen ORDER BY timestamp ASC"
    ).fetchall()
    conn.close()

    per_dag_uur: dict[str, dict] = {}
    for r in rijen:
        dt_lokaal = datetime.fromisoformat(r["timestamp"]).astimezone(LOCAL_TZ)
        sleutel = dt_lokaal.strftime("%Y-%m-%dT%H")
        if sleutel not in per_dag_uur:
            per_dag_uur[sleutel] = {"uur": dt_lokaal.hour, "eerste": r["energy_export_kwh"]}
        per_dag_uur[sleutel]["laatste"] = r["energy_export_kwh"]

    per_uur: dict[int, list[float]] = {u: [] for u in range(24)}
    for v in per_dag_uur.values():
        delta = max(0.0, v["laatste"] - v["eerste"])
        per_uur[v["uur"]].append(delta)

    resultaat = [
        {
            "uur": f"{u:02d}:00",
            "gemiddeld_kwh": round(sum(waarden) / len(waarden), 3) if waarden else 0.0,
        }
        for u, waarden in sorted(per_uur.items())
    ]
    cache["data"] = resultaat
    cache["opgehaald_op"] = nu
    return resultaat


def _schaaltarief(schalen: list[tuple[float, float, float]], volume: float) -> float:
    for laag, hoog, tarief in schalen:
        if laag <= volume < hoog:
            return tarief
    return schalen[-1][2]


def _cumulatief_dynamisch_vanaf(kosten: list[dict], vanaf: date) -> float:
    """Cumulatieve dynamische-tarief-kosten uit kosten_vergelijking()
    herberekend vanaf een gekozen datum i.p.v. vanaf het allereerste begin
    van de logging (voor als je zelf een latere ingangsdatum kiest)."""
    baseline = 0.0
    laatste = 0.0
    for rij in kosten:
        dag = datetime.strptime(rij["dag"], "%Y-%m-%d").date()
        laatste = rij["cumulatief_dynamisch"]
        if dag < vanaf:
            baseline = rij["cumulatief_dynamisch"]
    return laatste - baseline


def geschatte_rekening(kosten: list[dict], vanaf: date | None = None) -> dict | None:
    """Proforma-schatting van de energierekening: energiekosten (dynamisch
    tarief) + alle vaste kosten en heffingen uit het Vandebron-contract,
    voor zowel elektriciteit als gas.

    Standaard (`vanaf=None`) begint dit bij het begin van de logging
    (2 juli 2026). Kies je zelf een `vanaf`-datum:
    - ná het begin van de logging: het "echte deel" wordt gewoon herrekend
      over die kortere, recentere periode;
    - vóór het begin van de logging: het deel tussen `vanaf` en het begin
      van de logging is een **schatting** (gemiddeld dagverbruik uit de wél
      gemeten periode x de EPEX-dagprijs van die dag), apart teruggegeven
      als `posten_geschat`/`dagen_geschat` zodat de template dit duidelijk
      gescheiden kan tonen.

    Twee bewuste vereenvoudigingen, zichtbaar in 'kanttekeningen':
    - de schaal voor vaste terugleveringskosten is gebaseerd op een
      extrapolatie van de teruglevering tot nu toe naar een heel jaar --
      met alleen zomerdata valt dat te hoog uit;
    - energiebelasting rekent met de laagste schijf, wat correct is zolang
      het jaarverbruik onder de eerste schijfgrens blijft (ruim het geval
      bij deze volumes)."""
    if not kosten:
        return None

    conn = _connect()
    globale_eerste = conn.execute("SELECT * FROM metingen ORDER BY timestamp ASC LIMIT 1").fetchone()
    laatste = conn.execute("SELECT * FROM metingen ORDER BY timestamp DESC LIMIT 1").fetchone()
    if globale_eerste is None or laatste is None:
        conn.close()
        return None

    eerste_dag_logging = datetime.fromisoformat(globale_eerste["timestamp"]).date()
    laatste_dag = datetime.fromisoformat(laatste["timestamp"]).date()

    effective_start = vanaf if vanaf is not None else eerste_dag_logging
    geschat_start = effective_start if effective_start < eerste_dag_logging else None
    echt_start = max(effective_start, eerste_dag_logging)

    eerste = conn.execute(
        "SELECT * FROM metingen WHERE timestamp >= ? ORDER BY timestamp ASC LIMIT 1",
        (echt_start.isoformat(),),
    ).fetchone()
    eerste_met_gas = conn.execute(
        "SELECT * FROM metingen WHERE timestamp >= ? AND gas_m3 IS NOT NULL ORDER BY timestamp ASC LIMIT 1",
        (echt_start.isoformat(),),
    ).fetchone()

    aantal_dagen = max(1, (laatste_dag - echt_start).days + 1)
    import_totaal = max(0.0, laatste["energy_import_kwh"] - eerste["energy_import_kwh"])
    export_totaal = max(0.0, laatste["energy_export_kwh"] - eerste["energy_export_kwh"])

    kanttekeningen = []
    posten = []

    # --- Elektriciteit ---
    # "Energiekosten (dynamisch tarief)" komt uit de EPEX ALL_IN-marktprijs
    # (price_fetcher.py/energyzero-bibliotheek) -- dat is de gangbare
    # betekenis van "ALL_IN" in de Nederlandse dynamische-energiemarkt:
    # kale marktprijs + energiebelasting + btw zijn daar al in verwerkt.
    # Energiebelasting hoort dus NIET nogmaals als aparte post opgeteld te
    # worden (dat was eerder een dubbeltelling). Alleen de
    # Vandebron-specifieke inkoopvergoeding (een leveranciersopslag, geen
    # marktgegeven) zit daar niet in en wordt apart toegevoegd, inclusief
    # de 21% btw die Vandebron bevestigde (kale tarief + inkoopvergoeding +
    # energiebelasting samen, dan btw).
    kwh_kosten = _cumulatief_dynamisch_vanaf(kosten, echt_start)
    vaste_leveringskosten = config.ELEKTRICITEIT_VASTE_LEVERINGSKOSTEN_PER_DAG * aantal_dagen
    netbeheer = config.ELEKTRICITEIT_NETBEHEERKOSTEN_PER_DAG * aantal_dagen
    vermindering = config.ELEKTRICITEIT_VERMINDERING_ENERGIEBELASTING_PER_DAG * aantal_dagen

    export_per_jaar_geschat = export_totaal / aantal_dagen * 365.25
    terugleverkosten_tarief = _schaaltarief(
        config.ELEKTRICITEIT_VASTE_TERUGLEVERINGSKOSTEN_SCHALEN, export_per_jaar_geschat
    )
    terugleverkosten = terugleverkosten_tarief * aantal_dagen
    if aantal_dagen < 90:
        kanttekeningen.append(
            "vaste terugleveringskosten zijn gebaseerd op een schatting van je jaarlijkse "
            "teruglevering met nog maar een paar weken (zomer)data -- dat valt te hoog uit"
        )

    inkoopvergoeding = (import_totaal - export_totaal) * config.ELEKTRICITEIT_INKOOPVERGOEDING_KWH * 1.21
    if export_totaal > import_totaal:
        kanttekeningen.append(
            "inkoopvergoeding op teruglevering wordt op de jaarafrekening gecorrigeerd zodra "
            "je over het jaar meer teruglevert dan je verbruikt -- dat is hier (nog) niet verrekend"
        )

    posten += [
        {"naam": "Energiekosten (dynamisch tarief, incl. energiebelasting en btw)", "bedrag": round(kwh_kosten, 2), "categorie": "elektriciteit"},
        {"naam": "Vaste leveringskosten (elektriciteit)", "bedrag": round(vaste_leveringskosten, 2), "categorie": "elektriciteit"},
        {"naam": "Netbeheerkosten (elektriciteit)", "bedrag": round(netbeheer, 2), "categorie": "elektriciteit"},
        {"naam": "Vermindering energiebelasting", "bedrag": round(-vermindering, 2), "categorie": "elektriciteit"},
        {"naam": "Vaste terugleveringskosten", "bedrag": round(terugleverkosten, 2), "categorie": "elektriciteit"},
        {"naam": "Inkoopvergoeding (elektriciteit, incl. btw)", "bedrag": round(inkoopvergoeding, 2), "categorie": "elektriciteit"},
    ]
    totaal = (
        kwh_kosten + vaste_leveringskosten + netbeheer
        - vermindering + terugleverkosten + inkoopvergoeding
    )

    # --- Gas ---
    if eerste_met_gas is not None and laatste["gas_m3"] is not None:
        gas_totaal = max(0.0, laatste["gas_m3"] - eerste_met_gas["gas_m3"])
        gas_dagen = (
            laatste_dag - datetime.fromisoformat(eerste_met_gas["timestamp"]).astimezone(LOCAL_TZ).date()
        ).days + 1
        gas_energiebelasting_tarief = _schaaltarief(config.GAS_ENERGIEBELASTING_SCHALEN, gas_totaal)
        gas_kosten = gas_totaal * (
            config.GAS_LEVERING_M3 + config.GAS_REGIOTOESLAG_M3
            + config.GAS_LOKAAL_INVESTEREN_M3 + gas_energiebelasting_tarief
            + config.GAS_INKOOPVERGOEDING_M3
        )
        gas_vast = (config.GAS_VASTE_LEVERINGSKOSTEN_PER_DAG + config.GAS_NETBEHEERKOSTEN_PER_DAG) * gas_dagen
        posten += [
            {"naam": "Gasverbruik (incl. inkoopvergoeding)", "bedrag": round(gas_kosten, 2), "categorie": "gas"},
            {"naam": "Vaste kosten gas", "bedrag": round(gas_vast, 2), "categorie": "gas"},
        ]
        totaal += gas_kosten + gas_vast
        kanttekeningen.append(
            "gasverbruik wordt pas sinds 28-07-2026 gelogd -- de weergegeven gaskosten "
            "gelden dus over een kortere periode dan de elektriciteitskosten hierboven"
        )
    else:
        kanttekeningen.append("nog geen gasdata beschikbaar")

    # --- Geschat deel (vóór het begin van de logging, alleen als je zelf
    # een eerdere ingangsdatum kiest) -- gemiddeld dagverbruik uit de wél
    # gemeten periode x de EPEX-dagprijs van die dag. Zodra er een echte
    # historische export (bijv. via slimmemeterportal.nl) voor (een deel
    # van) deze dagen beschikbaar is, hoort die als ECHTE data te worden
    # meegenomen i.p.v. deze schatting -- dat is nog niet geïmplementeerd.
    posten_geschat = None
    dagen_geschat = 0
    if geschat_start is not None:
        dagen_geschat = (eerste_dag_logging - geschat_start).days
        profiel_import = import_totaal / aantal_dagen if aantal_dagen else 0.0
        profiel_export = export_totaal / aantal_dagen if aantal_dagen else 0.0

        prijzen_rijen = conn.execute(
            "SELECT kwartier_start, prijs_kwh FROM prijzen WHERE kwartier_start >= ? AND kwartier_start < ?",
            (geschat_start.isoformat(), eerste_dag_logging.isoformat()),
        ).fetchall()
        prijs_per_dag: dict[str, list[float]] = {}
        for r in prijzen_rijen:
            prijs_per_dag.setdefault(r["kwartier_start"][:10], []).append(r["prijs_kwh"])
        gem_prijs_per_dag = {dag: sum(v) / len(v) for dag, v in prijs_per_dag.items()}

        # Echte historische kwartierdata van slimmemeterportal.nl (je eigen
        # slimme meter, terug tot 2015) heeft voorrang boven het gemiddeld
        # dagprofiel -- alleen dagen die daar ontbreken worden nog geschat.
        historie = smp.historie_lezen()
        elek_historie = historie.get("elektriciteit", {})

        energie_geschat = 0.0
        dagen_zonder_prijs = 0
        dagen_echt_extern = 0
        netto_kwh_totaal = 0.0
        dag_cursor = geschat_start
        while dag_cursor < eerste_dag_logging:
            sleutel = dag_cursor.isoformat()
            dag_echt = elek_historie.get(sleutel)
            if dag_echt is not None:
                dag_import, dag_export = dag_echt["import"], dag_echt["export"]
                dagen_echt_extern += 1
            else:
                dag_import, dag_export = profiel_import, profiel_export
            netto_kwh_totaal += dag_import - dag_export

            prijs = gem_prijs_per_dag.get(sleutel)
            if prijs is None:
                dagen_zonder_prijs += 1
            else:
                energie_geschat += (dag_import - dag_export) * prijs
            dag_cursor += timedelta(days=1)

        vaste_leveringskosten_g = config.ELEKTRICITEIT_VASTE_LEVERINGSKOSTEN_PER_DAG * dagen_geschat
        netbeheer_g = config.ELEKTRICITEIT_NETBEHEERKOSTEN_PER_DAG * dagen_geschat
        vermindering_g = config.ELEKTRICITEIT_VERMINDERING_ENERGIEBELASTING_PER_DAG * dagen_geschat
        terugleverkosten_g = terugleverkosten_tarief * dagen_geschat
        inkoopvergoeding_g = netto_kwh_totaal * config.ELEKTRICITEIT_INKOOPVERGOEDING_KWH * 1.21

        label_suffix = "geschat" if dagen_echt_extern < dagen_geschat else "slimmemeterportal.nl"
        posten_geschat = [
            {"naam": f"Energiekosten (dynamisch tarief, {label_suffix})", "bedrag": round(energie_geschat, 2), "categorie": "elektriciteit"},
            {"naam": "Vaste leveringskosten (elektriciteit, geschat)", "bedrag": round(vaste_leveringskosten_g, 2), "categorie": "elektriciteit"},
            {"naam": "Netbeheerkosten (elektriciteit, geschat)", "bedrag": round(netbeheer_g, 2), "categorie": "elektriciteit"},
            {"naam": "Vermindering energiebelasting (geschat)", "bedrag": round(-vermindering_g, 2), "categorie": "elektriciteit"},
            {"naam": "Vaste terugleveringskosten (geschat)", "bedrag": round(terugleverkosten_g, 2), "categorie": "elektriciteit"},
            {"naam": f"Inkoopvergoeding (elektriciteit, {label_suffix})", "bedrag": round(inkoopvergoeding_g, 2), "categorie": "elektriciteit"},
        ]
        if eerste_met_gas is not None:
            gas_vast_g = (config.GAS_VASTE_LEVERINGSKOSTEN_PER_DAG + config.GAS_NETBEHEERKOSTEN_PER_DAG) * dagen_geschat
            posten_geschat.append(
                {"naam": "Vaste kosten gas (geschat)", "bedrag": round(gas_vast_g, 2), "categorie": "gas"}
            )

        totaal += sum(p["bedrag"] for p in posten_geschat)

        kanttekening_geschat = (
            f"Vanaf {geschat_start.strftime('%d-%m-%Y')} tot {eerste_dag_logging.strftime('%d-%m-%Y')} "
            "is er geen eigen P1-meterdata."
        )
        if dagen_echt_extern == dagen_geschat:
            kanttekening_geschat += (
                " Het verbruik in deze periode komt van je eigen slimme meter via "
                "slimmemeterportal.nl (echte data), niet uit een schatting."
            )
        elif dagen_echt_extern:
            kanttekening_geschat += (
                f" Voor {dagen_echt_extern} van de {dagen_geschat} dagen is dit echte data van je "
                "slimme meter (via slimmemeterportal.nl); voor de rest een schatting op basis van je "
                "gemiddelde verbruik in de wél gemeten periode."
            )
        else:
            kanttekening_geschat += (
                " Deze regels zijn een schatting op basis van je gemiddelde verbruik in de wél "
                "gemeten periode."
            )
        if dagen_zonder_prijs:
            kanttekening_geschat += (
                f" Voor {dagen_zonder_prijs} dag(en) ontbrak zelfs een prijs -- die dagen tellen niet "
                "mee in de berekening."
            )
        kanttekeningen.append(kanttekening_geschat)

    conn.close()

    return {
        "sinds": (geschat_start or echt_start).strftime("%d-%m-%Y"),
        "eerste_meetdatum": eerste_dag_logging.strftime("%d-%m-%Y"),
        "aantal_dagen": aantal_dagen + dagen_geschat,
        "posten": posten,
        "posten_geschat": posten_geschat,
        "dagen_geschat": dagen_geschat,
        "totaal": round(totaal, 2),
        "kanttekeningen": kanttekeningen,
    }


def _dagelijkse_totaalkosten(vanaf: date, tot: date, kosten: list[dict]) -> dict[str, float]:
    """Totale kosten (elektriciteit, vaste kosten + variabel) per
    kalenderdag over het opgegeven bereik -- voor de uitsplitsingsgrafiek
    onder de rekening. Combineert echte dagen (uit kosten_vergelijking(),
    per dag het verschil in cumulatief_dynamisch) met geschatte dagen
    (gemiddeld dagprofiel x EPEX-dagprijs) vóór het begin van de logging."""
    conn = _connect()
    globale_eerste = conn.execute("SELECT * FROM metingen ORDER BY timestamp ASC LIMIT 1").fetchone()
    laatste = conn.execute("SELECT * FROM metingen ORDER BY timestamp DESC LIMIT 1").fetchone()
    if globale_eerste is None or laatste is None:
        conn.close()
        return {}
    eerste_dag_logging = datetime.fromisoformat(globale_eerste["timestamp"]).date()

    vaste_per_dag = (
        config.ELEKTRICITEIT_VASTE_LEVERINGSKOSTEN_PER_DAG
        + config.ELEKTRICITEIT_NETBEHEERKOSTEN_PER_DAG
        - config.ELEKTRICITEIT_VERMINDERING_ENERGIEBELASTING_PER_DAG
    )

    resultaat: dict[str, float] = {}

    dynamisch_per_dag = {}
    vorige_cum = 0.0
    for rij in kosten:
        dynamisch_per_dag[rij["dag"]] = rij["cumulatief_dynamisch"] - vorige_cum
        vorige_cum = rij["cumulatief_dynamisch"]

    dag_cursor = max(vanaf, eerste_dag_logging)
    while dag_cursor <= tot:
        sleutel = dag_cursor.isoformat()
        resultaat[sleutel] = dynamisch_per_dag.get(sleutel, 0.0) + vaste_per_dag
        dag_cursor += timedelta(days=1)

    if vanaf < eerste_dag_logging:
        eerste = conn.execute(
            "SELECT * FROM metingen WHERE timestamp >= ? ORDER BY timestamp ASC LIMIT 1",
            (eerste_dag_logging.isoformat(),),
        ).fetchone()
        laatste_dag_echt = datetime.fromisoformat(laatste["timestamp"]).date()
        aantal_dagen_echt = max(1, (laatste_dag_echt - eerste_dag_logging).days + 1)
        profiel_import = max(0.0, laatste["energy_import_kwh"] - eerste["energy_import_kwh"]) / aantal_dagen_echt
        profiel_export = max(0.0, laatste["energy_export_kwh"] - eerste["energy_export_kwh"]) / aantal_dagen_echt

        prijzen_rijen = conn.execute(
            "SELECT kwartier_start, prijs_kwh FROM prijzen WHERE kwartier_start >= ? AND kwartier_start < ?",
            (vanaf.isoformat(), eerste_dag_logging.isoformat()),
        ).fetchall()
        prijs_per_dag: dict[str, list[float]] = {}
        for r in prijzen_rijen:
            prijs_per_dag.setdefault(r["kwartier_start"][:10], []).append(r["prijs_kwh"])
        gem_prijs_per_dag = {d: sum(v) / len(v) for d, v in prijs_per_dag.items()}

        elek_historie = smp.historie_lezen().get("elektriciteit", {})

        dag_cursor = vanaf
        while dag_cursor < eerste_dag_logging:
            sleutel = dag_cursor.isoformat()
            prijs = gem_prijs_per_dag.get(sleutel)
            if prijs is not None:
                dag_echt = elek_historie.get(sleutel)
                dag_import, dag_export = (
                    (dag_echt["import"], dag_echt["export"]) if dag_echt is not None
                    else (profiel_import, profiel_export)
                )
                resultaat[sleutel] = (dag_import - dag_export) * prijs + vaste_per_dag
            dag_cursor += timedelta(days=1)

    conn.close()
    return resultaat


def rekening_uitsplitsing(vanaf: date, tot: date, kosten: list[dict]) -> list[dict]:
    """Kosten per periode (dag/week/maand/jaar, automatisch gekozen op de
    lengte van het bereik) voor de grafiek onder de geschatte rekening."""
    dagkosten = _dagelijkse_totaalkosten(vanaf, tot, kosten)
    if not dagkosten:
        return []

    dagen_in_bereik = (tot - vanaf).days + 1
    if dagen_in_bereik <= 31:
        granulariteit = "dag"
    elif dagen_in_bereik <= 84:
        granulariteit = "week"
    elif dagen_in_bereik <= 730:
        granulariteit = "maand"
    else:
        granulariteit = "jaar"

    per_bucket: dict[str, float] = {}
    labels: dict[str, str] = {}
    for dag_iso, bedrag in dagkosten.items():
        dag = date.fromisoformat(dag_iso)
        if granulariteit == "dag":
            sleutel, label = dag_iso, f"{dag.day} {_MAANDNAMEN[dag.month - 1]}"
        elif granulariteit == "week":
            maandag = dag - timedelta(days=dag.weekday())
            _, iso_week, _ = dag.isocalendar()
            sleutel, label = maandag.isoformat(), f"wk {iso_week}"
        elif granulariteit == "maand":
            sleutel = f"{dag.year}-{dag.month:02d}"
            label = f"{_MAANDNAMEN[dag.month - 1]} {dag.year}"
        else:
            sleutel, label = str(dag.year), str(dag.year)
        labels[sleutel] = label
        per_bucket[sleutel] = per_bucket.get(sleutel, 0.0) + bedrag

    return [
        {"label": labels[sleutel], "bedrag": round(bedrag, 2)}
        for sleutel, bedrag in sorted(per_bucket.items())
    ]


_KOSTEN_VERGELIJKING_CACHE: dict = {"data": None, "opgehaald_op": 0.0}
_KOSTEN_VERGELIJKING_CACHE_SECONDEN = 300  # 5 min


def kosten_vergelijking() -> list[dict]:
    """Cumulatieve kosten vast vs. dynamisch tarief, per dag, over de hele
    beschikbare geschiedenis -- zelfde rekenlogica als
    energieproject/simulator.py op de Pi (bewust gedupliceerd, zie
    CLAUDE.md: dit dashboard raakt de logger-code niet aan). Dit overzicht
    is bewust niet aan de dag/week/maand/jaar-navigatie gekoppeld: het gaat
    juist om het totaalbeeld sinds het begin van de logging.

    5 minuten in-memory gecached (20-08-2026): deze query leest de VOLLE
    metingen-tabel (69k+ rijen en groeiend), wat op de externe SSD soms
    10-20 seconden duurde en tot "database is locked" leidde bij
    gelijktijdige schrijfacties van energy_logger.py. De cache verandert
    niets aan de uitkomst (metingen wijzigen niet met terugwerkende
    kracht), enkel hoe vaak de zware query opnieuw draait."""
    nu = time.time()
    cache = _KOSTEN_VERGELIJKING_CACHE
    if cache["data"] is not None and nu - cache["opgehaald_op"] < _KOSTEN_VERGELIJKING_CACHE_SECONDEN:
        return cache["data"]
    conn = _connect()
    metingen = conn.execute(
        "SELECT timestamp, energy_import_kwh, energy_export_kwh, "
        "energy_import_normaal_kwh, energy_import_dal_kwh, "
        "energy_export_normaal_kwh, energy_export_dal_kwh "
        "FROM metingen ORDER BY timestamp ASC"
    ).fetchall()
    prijzen = dict(conn.execute("SELECT kwartier_start, prijs_kwh FROM prijzen").fetchall())
    conn.close()

    per_kwartier: dict[str, dict] = {}
    for r in metingen:
        kwartier = _naar_kwartier_utc(r["timestamp"])
        waarden = dict(r)
        if kwartier not in per_kwartier:
            per_kwartier[kwartier] = {"eerste": waarden, "laatste": waarden}
        else:
            per_kwartier[kwartier]["laatste"] = waarden

    per_dag_kosten: dict[str, dict] = {}
    for kwartier, v in sorted(per_kwartier.items()):
        if kwartier not in prijzen:
            continue
        e, l = v["eerste"], v["laatste"]

        def delta(key: str) -> float:
            return max(0.0, l[key] - e[key])

        import_kwh = delta("energy_import_kwh")
        export_kwh = delta("energy_export_kwh")
        import_n = delta("energy_import_normaal_kwh")
        import_d = delta("energy_import_dal_kwh")
        export_n = delta("energy_export_normaal_kwh")
        export_d = delta("energy_export_dal_kwh")
        prijs = prijzen[kwartier]

        # Kale tarief + energiebelasting, dan 21% btw -- bevestigd door
        # Vandebron: het kale leveringstarief is exclusief energiebelasting
        # en btw. Geen inkoopvergoeding hier: die geldt specifiek voor
        # dynamische contracten, niet voor dit vaste-tarief-scenario.
        # `prijs` (dynamisch) is al all-in (zie geschatte_rekening), dus
        # voor een eerlijke vergelijking moet dit dat ook zijn.
        energiebelasting_tarief = config.ELEKTRICITEIT_ENERGIEBELASTING_SCHALEN[0][2]
        all_in_normaal = (config.ELEKTRICITEIT_NORMAAL_KWH + energiebelasting_tarief) * 1.21
        all_in_dal = (config.ELEKTRICITEIT_DAL_KWH + energiebelasting_tarief) * 1.21
        all_in_saldering_normaal = (config.ELEKTRICITEIT_SALDERING_NORMAAL_KWH + energiebelasting_tarief) * 1.21
        all_in_saldering_dal = (config.ELEKTRICITEIT_SALDERING_DAL_KWH + energiebelasting_tarief) * 1.21

        kosten_vast = (
            import_n * all_in_normaal
            + import_d * all_in_dal
            - export_n * all_in_saldering_normaal
            - export_d * all_in_saldering_dal
        )
        kosten_dyn = import_kwh * prijs - export_kwh * prijs

        dag = kwartier[:10]
        if dag not in per_dag_kosten:
            per_dag_kosten[dag] = {"vast": 0.0, "dynamisch": 0.0}
        per_dag_kosten[dag]["vast"] += kosten_vast
        per_dag_kosten[dag]["dynamisch"] += kosten_dyn

    cumulatief_vast = cumulatief_dyn = 0.0
    resultaat = []
    for dag in sorted(per_dag_kosten):
        cumulatief_vast += per_dag_kosten[dag]["vast"]
        cumulatief_dyn += per_dag_kosten[dag]["dynamisch"]
        resultaat.append({
            "dag": dag,
            "cumulatief_vast": round(cumulatief_vast, 2),
            "cumulatief_dynamisch": round(cumulatief_dyn, 2),
        })
    cache["data"] = resultaat
    cache["opgehaald_op"] = nu
    return resultaat


# --- Voorschot (eigen invoer, geen meetdata) --------------------------------
# Puur wat Jacob zelf maandelijks aan zijn energieleverancier betaalt --
# geen afgeleide meetdata, dus opgeslagen in een eigen JSON-bestand naast
# de (read-only) logger-database, niet erin.

def voorschotten_lezen() -> list[dict]:
    """Alle voorschotregels, oplopend op datum: [{'vanaf': 'YYYY-MM-DD',
    'bedrag': 123.45}, ...]."""
    if not os.path.exists(config.VOORSCHOT_PAD):
        return []
    with open(config.VOORSCHOT_PAD, "r", encoding="utf-8") as f:
        regels = json.load(f)
    return sorted(regels, key=lambda r: r["vanaf"])


def voorschot_toevoegen(vanaf: date, bedrag: float) -> None:
    """Voegt een voorschotregel toe, of overschrijft de bestaande regel voor
    diezelfde maand als die al bestaat."""
    regels = voorschotten_lezen()
    vanaf_iso = vanaf.isoformat()
    regels = [r for r in regels if r["vanaf"] != vanaf_iso]
    regels.append({"vanaf": vanaf_iso, "bedrag": round(bedrag, 2)})
    regels.sort(key=lambda r: r["vanaf"])
    os.makedirs(os.path.dirname(config.VOORSCHOT_PAD), exist_ok=True)
    with open(config.VOORSCHOT_PAD, "w", encoding="utf-8") as f:
        json.dump(regels, f, ensure_ascii=False, indent=2)


def voorschot_voor_periode(vanaf: date, tot: date) -> float | None:
    """Som van het geldende voorschotbedrag per maand in [vanaf, tot] --
    het laatst bekende bedrag vóór of op een maand geldt door tot een
    nieuwe regel. None als er nog geen enkele voorschotregel is."""
    regels = voorschotten_lezen()
    if not regels:
        return None

    totaal = 0.0
    maand_cursor = vanaf.replace(day=1)
    while maand_cursor <= tot:
        geldend = None
        for r in regels:
            if r["vanaf"] <= maand_cursor.isoformat():
                geldend = r["bedrag"]
            else:
                break
        if geldend is not None:
            dagen_in_maand_in_bereik = sum(
                1 for d in _dagen_in_maand(maand_cursor) if vanaf <= d <= tot
            )
            dagen_in_maand_totaal = len(_dagen_in_maand(maand_cursor))
            totaal += geldend * dagen_in_maand_in_bereik / dagen_in_maand_totaal
        if maand_cursor.month == 12:
            maand_cursor = maand_cursor.replace(year=maand_cursor.year + 1, month=1)
        else:
            maand_cursor = maand_cursor.replace(month=maand_cursor.month + 1)
    return round(totaal, 2)


def _dagen_in_maand(eerste_van_maand: date) -> list[date]:
    if eerste_van_maand.month == 12:
        volgende_maand = eerste_van_maand.replace(year=eerste_van_maand.year + 1, month=1)
    else:
        volgende_maand = eerste_van_maand.replace(month=eerste_van_maand.month + 1)
    dagen = []
    d = eerste_van_maand
    while d < volgende_maand:
        dagen.append(d)
        d += timedelta(days=1)
    return dagen
