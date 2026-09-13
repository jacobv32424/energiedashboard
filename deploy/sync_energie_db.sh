#!/bin/bash
# Haalt een consistente kopie van de energie-database op van plex (waar
# energy_logger.py 'm continu bijwerkt op de PortableSSD) naar thuis se
# eigen schijf. Draait als systemd-timer op thuis zelf, niet op plex --
# dit dashboard raakt de logger-code op plex niet aan (zie CLAUDE.md),
# dit script leest er alleen van.
#
# ".backup" (i.p.v. een ruwe bestandskopie/rsync van het .db-bestand) zodat
# een gelijktijdige schrijfactie van de logger nooit een kapotte/halve
# kopie oplevert. Sleutel ~/.ssh/id_thuis_energiedb (alleen voor dit doel,
# publieke helft in plex se authorized_keys, 12-09-2026).
set -euo pipefail

BRON_TIJDELIJK="/tmp/energie-sync-thuis.db"
BESTEMMING="/media/thuis/USB-SCHIJF-1TB/energiedashboard/energie.db"

ssh plex "sqlite3 /media/jacob/PortableSSD/energieproject/data/energie.db \".backup '$BRON_TIJDELIJK'\""
scp -q "plex:$BRON_TIJDELIJK" "$BESTEMMING.nieuw"
mv "$BESTEMMING.nieuw" "$BESTEMMING"
ssh plex "rm -f $BRON_TIJDELIJK"
