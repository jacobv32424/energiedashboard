import os
import threading
import time
from datetime import date, timezone, datetime as dt

import markdown
from flask import Flask, redirect, render_template, request, url_for

import config
import dataset

app = Flask(__name__)

_MAANDNAMEN = [
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
]


@app.route("/")
def dashboard():
    periode = request.args.get("periode", "dag")
    if periode not in dataset._PERIODES:
        periode = "dag"

    datum_param = request.args.get("datum", "")
    try:
        referentie = date.fromisoformat(datum_param) if datum_param else dt.now(timezone.utc).date()
    except ValueError:
        referentie = dt.now(timezone.utc).date()

    rekening_vanaf_param = request.args.get("rekening_vanaf", "")
    try:
        rekening_vanaf = date.fromisoformat(rekening_vanaf_param) if rekening_vanaf_param else None
    except ValueError:
        rekening_vanaf = None

    navigatie = dataset.periode_navigatie(periode, referentie)
    kosten = dataset.kosten_vergelijking()
    rekening = dataset.geschatte_rekening(kosten, vanaf=rekening_vanaf)

    uitsplitsing = []
    if rekening:
        vanaf_grafiek = rekening_vanaf or dt.strptime(rekening["eerste_meetdatum"], "%d-%m-%Y").date()
        tot_grafiek = dt.now(timezone.utc).date()
        uitsplitsing = dataset.rekening_uitsplitsing(vanaf_grafiek, tot_grafiek, kosten)
        voorschot_ontvangen = dataset.voorschot_voor_periode(vanaf_grafiek, tot_grafiek)
    else:
        voorschot_ontvangen = None

    return render_template(
        "dashboard.html",
        stand=dataset.huidige_stand(),
        totaal=dataset.totaal_bespaard(kosten),
        rekening=rekening,
        rekening_uitsplitsing=uitsplitsing,
        rekening_vanaf=rekening_vanaf_param,
        zelfvoorzienendheid=dataset.zelfvoorzienendheid(vanaf=rekening_vanaf),
        voorschotten=dataset.voorschotten_lezen(),
        voorschot_ontvangen=voorschot_ontvangen,
        vermogen=dataset.vermogen_serie(periode, referentie),
        verbruik=dataset.verbruik_per_periode(periode, referentie),
        gas=dataset.gas_per_periode(periode, referentie),
        zonpatroon=dataset.zonpatroon_per_uur(),
        kosten=kosten,
        periode=periode,
        navigatie=navigatie,
        config=config,
        database_pad=config.DB_PATH,
    )


@app.route("/voorschot", methods=["POST"])
def voorschot_toevoegen():
    vanaf_param = request.form.get("vanaf", "")
    bedrag_param = request.form.get("bedrag", "")
    try:
        vanaf = date.fromisoformat(vanaf_param)
        bedrag = float(bedrag_param.replace(",", "."))
        dataset.voorschot_toevoegen(vanaf, bedrag)
    except (ValueError, TypeError):
        pass
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/introductie")
def introductie():
    return render_template("introductie.html")


@app.route("/handleiding")
def handleiding():
    pad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Handleiding.md")
    with open(pad, "r", encoding="utf-8") as f:
        tekst = f.read()
    html = markdown.markdown(
        tekst, extensions=["tables", "toc"], extension_configs={"toc": {"toc_depth": "2-3"}},
    )
    return render_template("handleiding.html", inhoud=html)


_VRAGEN_TABBLAD_NAMEN = ["Dashboard", "Voorschot", "Zelfvoorzienendheid", "Rekening", "Algemeen"]
_VRAGEN_STATUSSEN = ("open", "beantwoord", "bouwen", "gebouwd", "toegelicht", "afgewezen")


@app.route("/vragen")
def vragen_overzicht():
    status_filter = request.args.get("status", "")
    gebied_filter = request.args.get("gebied", "")
    return render_template(
        "vragen.html",
        vragen=dataset.alle_vragen(status_filter, gebied_filter),
        gebieden=dataset.alle_vragen_gebieden(),
        tabblad_namen=_VRAGEN_TABBLAD_NAMEN,
        statistiek=dataset.vragen_statistiek(),
        statussen=_VRAGEN_STATUSSEN,
        status_filter=status_filter, gebied_filter=gebied_filter,
    )


@app.route("/vragen/toevoegen", methods=["POST"])
def vragen_toevoegen():
    onderwerp = (request.form.get("onderwerp") or "").strip()
    vraag = (request.form.get("vraag") or "").strip()
    if onderwerp and vraag:
        dataset.vraag_toevoegen(
            onderwerp, vraag,
            gebied=(request.form.get("gebied") or "").strip(),
            toelichting=(request.form.get("toelichting") or "").strip(),
            prioriteit=request.form.get("prioriteit", "normaal"),
        )
    return redirect(url_for("vragen_overzicht"))


@app.route("/vragen/<int:vraag_id>/beantwoorden", methods=["POST"])
def vragen_beantwoorden(vraag_id):
    dataset.vraag_beantwoorden(vraag_id, request.form.get("antwoord", ""), request.form.get("actie", ""))
    return redirect(url_for("vragen_overzicht"))


@app.route("/vragen/<int:vraag_id>/klaar-om-te-bouwen", methods=["POST"])
def vragen_klaar_om_te_bouwen(vraag_id):
    dataset.vraag_klaar_om_te_bouwen(vraag_id)
    return redirect(url_for("vragen_overzicht"))


@app.route("/vragen/<int:vraag_id>/gebouwd", methods=["POST"])
def vragen_gebouwd(vraag_id):
    dataset.vraag_gebouwd(vraag_id, dt.now().strftime("%d-%m-%Y"), request.form.get("actie", ""))
    return redirect(url_for("vragen_overzicht"))


@app.route("/vragen/<int:vraag_id>/toegelicht", methods=["POST"])
def vragen_toegelicht(vraag_id):
    dataset.vraag_toegelicht(vraag_id, dt.now().strftime("%d-%m-%Y"))
    return redirect(url_for("vragen_overzicht"))


@app.route("/vragen/<int:vraag_id>/afwijzen", methods=["POST"])
def vragen_afwijzen(vraag_id):
    dataset.vraag_afwijzen(vraag_id, request.form.get("reden", ""))
    return redirect(url_for("vragen_overzicht"))


# Cache-ververser (20-08-2026) -- kosten_vergelijking()/zonpatroon_per_uur()
# lezen de volle metingen-tabel (traag op de externe SSD) en zijn 5 min
# gecached, maar de EERSTE bezoeker na een herstart of na 5 min stilte
# trof nog steeds de trage, "koude" berekening (~15-16 sec). Deze
# achtergrondthread ververst beide caches elke 4 min -- korter dan hun
# 5-minuten-geldigheid -- zodat ze nooit koud worden zolang de service
# draait. Een bezoeker treft dus altijd de warme (snelle) cache.
def _cache_ververser() -> None:
    while True:
        try:
            dataset.kosten_vergelijking()
            dataset.zonpatroon_per_uur()
        except Exception:
            pass  # de achtergrondthread mag nooit stoppen door één mislukte poging
        time.sleep(240)  # 4 min, ruim binnen de 5-minuten cache-geldigheid


if __name__ == "__main__":
    threading.Thread(target=_cache_ververser, daemon=True).start()
    app.run(host="0.0.0.0", port=8421, debug=False)
