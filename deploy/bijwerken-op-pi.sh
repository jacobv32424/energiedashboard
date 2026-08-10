#!/bin/bash
# Werkt de Energiedashboard-installatie op de Pi (host "plex") bij met de
# laatste code van deze laptop, en herstart de service.
#
# Draai dit vanaf je LAPTOP (niet op de Pi zelf):
#   bash deploy/bijwerken-op-pi.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PI_HOST="plex"
PI_PAD="/opt/energiedashboard"

echo "Code overzetten naar $PI_HOST:$PI_PAD ..."
ssh "$PI_HOST" "sudo mkdir -p $PI_PAD && sudo chown jacob:jacob $PI_PAD"
rsync -avz --delete \
  --exclude .venv --exclude __pycache__ --exclude dev_data --exclude deploy \
  "$PROJECT_DIR"/ "$PI_HOST:$PI_PAD/"

echo "Service-bestand installeren ..."
scp "$PROJECT_DIR/deploy/energiedashboard.service" "$PI_HOST:/tmp/energiedashboard.service"
ssh "$PI_HOST" "sudo mv /tmp/energiedashboard.service /etc/systemd/system/energiedashboard.service && sudo systemctl daemon-reload"

echo "Opslagmap voor voorschot/historie-cache aanmaken op de Pi ..."
ssh "$PI_HOST" "mkdir -p /media/jacob/PortableSSD/energiedashboard"

if [ -f "$PROJECT_DIR/dev_data/slimmemeterportal_api_key.txt" ] && ! ssh "$PI_HOST" "[ -f /etc/energiedashboard/env ]"; then
  echo "slimmemeterportal.nl API-sleutel eenmalig naar de Pi zetten (buiten git, chmod 600) ..."
  API_KEY="$(cat "$PROJECT_DIR/dev_data/slimmemeterportal_api_key.txt")"
  ssh "$PI_HOST" "sudo mkdir -p /etc/energiedashboard && echo 'SLIMMEMETERPORTAL_API_KEY=$API_KEY' | sudo tee /etc/energiedashboard/env > /dev/null && sudo chmod 600 /etc/energiedashboard/env && sudo chown jacob:jacob /etc/energiedashboard/env"
fi

if [ -f "$PROJECT_DIR/dev_data/historie_slimmemeter.json" ]; then
  echo "Historische slimmemeterportal-cache meenemen naar de Pi ..."
  scp "$PROJECT_DIR/dev_data/historie_slimmemeter.json" "$PI_HOST:/media/jacob/PortableSSD/energiedashboard/historie_slimmemeter.json"
fi

echo "Afhankelijkheden bijwerken en service (her)starten op de Pi ..."
ssh "$PI_HOST" "cd $PI_PAD && [ -x .venv/bin/pip ] || python3 -m venv .venv && .venv/bin/pip install --quiet -r requirements.txt && sudo systemctl enable --now energiedashboard.service && sudo systemctl restart energiedashboard.service"

echo "Klaar. Status:"
ssh "$PI_HOST" "systemctl status energiedashboard.service --no-pager -l | head -10"
