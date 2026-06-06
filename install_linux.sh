#!/usr/bin/env bash
# Installe KarstPro (extrait karstpro.zip) + ses dependances Python sous Linux.
set -e
ZIP="$(cd "$(dirname "$0")" && pwd)/karstpro.zip"
PLUGDIR="$HOME/.local/share/QGIS/QGIS3/profiles/default/python/plugins"
DST="$PLUGDIR/karstpro"

echo "=== Installation du plugin KarstPro ==="
[ -f "$ZIP" ] || { echo "karstpro.zip introuvable a cote du script."; exit 1; }
mkdir -p "$PLUGDIR"
rm -rf "$DST"
if command -v unzip >/dev/null 2>&1; then
  unzip -oq "$ZIP" -d "$PLUGDIR"
else
  python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$ZIP" "$PLUGDIR"
fi
echo "  plugin installe dans : $DST"

echo
echo "=== Installation des dependances Python ==="
# Delegue au script eprouve embarque dans le plugin (gere apt/conda/Flatpak).
if [ -f "$DST/install_deps.sh" ]; then
  bash "$DST/install_deps.sh" || {
    echo "  Echec. Ouvre QGIS > Console Python, puis : import karstpro.install_dependencies"
  }
else
  echo "  install_deps.sh introuvable. Ouvre QGIS > Console Python, puis :"
  echo "      import karstpro.install_dependencies"
fi
echo
echo "Termine. Redemarre QGIS, puis active KarstPro dans les extensions."