from datetime import date, timezone, datetime as dt

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

    navigatie = dataset.periode_navigatie(periode, referentie)
    kosten = dataset.kosten_vergelijking()

    return render_template(
        "dashboard.html",
        stand=dataset.huidige_stand(),
        totaal=dataset.totaal_bespaard(kosten),
        vermogen=dataset.vermogen_serie(periode, referentie),
        verbruik=dataset.verbruik_per_periode(periode, referentie),
        zonpatroon=dataset.zonpatroon_per_uur(),
        kosten=kosten,
        periode=periode,
        navigatie=navigatie,
        instellingen={
            "tarief_normaal_kwh": config.VAST_TARIEF_NORMAAL_KWH,
            "tarief_dal_kwh": config.VAST_TARIEF_DAL_KWH,
            "terugleveren_normaal_kwh": config.VAST_TERUGLEVER_NORMAAL_KWH,
            "terugleveren_dal_kwh": config.VAST_TERUGLEVER_DAL_KWH,
            "database_pad": config.DB_PATH,
        },
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8421, debug=False)
