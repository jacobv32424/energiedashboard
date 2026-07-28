"""Leest (alleen-lezen) uit de energie.db die energy_logger.py/price_fetcher.py
op de Pi vullen, en levert kant-en-klare series voor het dashboard."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import config

LOCAL_TZ = ZoneInfo("Europe/Amsterdam")
_MAANDNAMEN = [
    "jan", "feb", "mrt", "apr", "mei", "jun",
    "jul", "aug", "sep", "okt", "nov", "dec",
]


def _connect():
    conn = sqlite3.connect(config.DB_PATH)
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


def zonpatroon_per_uur() -> list[dict]:
    """Gemiddelde teruglevering per uur van de dag, over alle beschikbare
    dagen -- laat zien wanneer de panelen typisch het meest opleveren,
    losstaand van welke specifieke dag je op dat moment bekijkt. Dit is
    het enige harde 'zonnegetal' dat uit P1-data valt te halen: de meter
    ziet alleen wat er het net op gaat, niet de rechtstreekse eigen
    consumptie van opgewekte stroom."""
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

    return [
        {
            "uur": f"{u:02d}:00",
            "gemiddeld_kwh": round(sum(waarden) / len(waarden), 3) if waarden else 0.0,
        }
        for u, waarden in sorted(per_uur.items())
    ]


def kosten_vergelijking() -> list[dict]:
    """Cumulatieve kosten vast vs. dynamisch tarief, per dag, over de hele
    beschikbare geschiedenis -- zelfde rekenlogica als
    energieproject/simulator.py op de Pi (bewust gedupliceerd, zie
    CLAUDE.md: dit dashboard raakt de logger-code niet aan). Dit overzicht
    is bewust niet aan de dag/week/maand/jaar-navigatie gekoppeld: het gaat
    juist om het totaalbeeld sinds het begin van de logging."""
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

        kosten_vast = (
            import_n * config.VAST_TARIEF_NORMAAL_KWH
            + import_d * config.VAST_TARIEF_DAL_KWH
            - export_n * config.VAST_TERUGLEVER_NORMAAL_KWH
            - export_d * config.VAST_TERUGLEVER_DAL_KWH
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
    return resultaat
