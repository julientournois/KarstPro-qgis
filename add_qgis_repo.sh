#!/usr/bin/env bash
# Enregistre le dépôt custom Karst Entry dans QGIS (mises à jour automatiques).
# Fermer QGIS avant de lancer ce script (sinon il écrase la modification à sa fermeture).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$SCRIPT_DIR/add_qgis_repo.py"

# Sous Linux, QGIS utilise en général le python3 système (PyQt5 installé via
# le paquet système, ex. python3-pyqt5) : pas d'interpréteur "python-qgis" à
# chercher séparément comme sous Windows.
if python3 -c "import PyQt5.QtCore" 2>/dev/null || python3 -c "import PyQt6.QtCore" 2>/dev/null; then
    exec python3 "$SCRIPT" "$@"
fi

echo "python3 ne trouve pas PyQt5 ni PyQt6." >&2
echo "Installez-le (ex. Debian/Ubuntu : sudo apt install python3-pyqt5)" >&2
echo "ou lancez avec le python3 fourni par votre distribution de QGIS." >&2
exit 1
