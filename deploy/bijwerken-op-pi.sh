#!/bin/bash
# Werkt de Energiedashboard-installatie op de Pi (host "thuis") bij met de
# laatste code van deze laptop, en herstart de service.
#
# Verhuisd van plex naar thuis op 12-09-2026 (plex draaide al veel: ook
# adressenboek, roladministratie, Huistechniek Verheul, Plex Media Server
# zelf). De energie-database blijft wel op plex (energy_logger.py logt
# daar de P1-meter) -- thuis haalt daar elke 5 min een consistente kopie
# van op, zie deploy/sync_energie_db.sh + de db-sync-timer die dit script
# ook installeert.
#
# Draai dit vanaf je LAPTOP (niet op de Pi zelf):
#   bash deploy/bijwerken-op-pi.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PI_HOST="thuis"
PI_PAD="/opt/energiedashboard"
OPSLAG="/media/thuis/USB-SCHIJF-1TB/energiedashboard"

echo "Code overzetten naar $PI_HOST:$PI_PAD ..."
ssh "$PI_HOST" "sudo mkdir -p $PI_PAD && sudo chown thuis:thuis $PI_PAD"
rsync -avz --delete \
  --exclude .venv --exclude __pycache__ --exclude dev_data --exclude .git \
  "$PROJECT_DIR"/ "$PI_HOST:$PI_PAD/"

echo "Service-bestanden installeren (hoofddienst + database-sync-timer) ..."
scp "$PROJECT_DIR/deploy/energiedashboard.service" "$PI_HOST:/tmp/energiedashboard.service"
scp "$PROJECT_DIR/deploy/energiedashboard-db-sync.service" "$PI_HOST:/tmp/energiedashboard-db-sync.service"
scp "$PROJECT_DIR/deploy/energiedashboard-db-sync.timer" "$PI_HOST:/tmp/energiedashboard-db-sync.timer"
ssh "$PI_HOST" "sudo mv /tmp/energiedashboard.service /etc/systemd/system/energiedashboard.service && \
  sudo mv /tmp/energiedashboard-db-sync.service /etc/systemd/system/energiedashboard-db-sync.service && \
  sudo mv /tmp/energiedashboard-db-sync.timer /etc/systemd/system/energiedashboard-db-sync.timer && \
  sudo systemctl daemon-reload"

echo "Opslagmap voor database-kopie/voorschot/historie-cache aanmaken op thuis ..."
ssh "$PI_HOST" "mkdir -p $OPSLAG"

if [ -f "$PROJECT_DIR/dev_data/slimmemeterportal_api_key.txt" ] && ! ssh "$PI_HOST" "[ -f /etc/energiedashboard/env ]"; then
  echo "slimmemeterportal.nl API-sleutel eenmalig naar thuis zetten (buiten git, chmod 600) ..."
  API_KEY="$(cat "$PROJECT_DIR/dev_data/slimmemeterportal_api_key.txt")"
  ssh "$PI_HOST" "sudo mkdir -p /etc/energiedashboard && echo 'SLIMMEMETERPORTAL_API_KEY=$API_KEY' | sudo tee /etc/energiedashboard/env > /dev/null && sudo chmod 600 /etc/energiedashboard/env && sudo chown thuis:thuis /etc/energiedashboard/env"
fi

if [ -f "$PROJECT_DIR/dev_data/historie_slimmemeter.json" ]; then
  echo "Historische slimmemeterportal-cache meenemen naar thuis ..."
  scp "$PROJECT_DIR/dev_data/historie_slimmemeter.json" "$PI_HOST:$OPSLAG/historie_slimmemeter.json"
fi

echo "Afhankelijkheden bijwerken en diensten (her)starten op thuis ..."
ssh "$PI_HOST" "cd $PI_PAD && chmod +x deploy/sync_energie_db.sh && [ -x .venv/bin/pip ] || python3 -m venv .venv && .venv/bin/pip install --quiet -r requirements.txt && sudo systemctl enable --now energiedashboard.service energiedashboard-db-sync.timer && sudo systemctl restart energiedashboard.service"

echo "Klaar. Status:"
ssh "$PI_HOST" "systemctl status energiedashboard.service --no-pager -l | head -10"
ssh "$PI_HOST" "systemctl status energiedashboard-db-sync.timer --no-pager -l | head -10"
