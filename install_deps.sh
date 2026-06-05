#!/usr/bin/env bash
# KarstPro — Installation des dépendances Python (Linux / macOS)
# Détecte automatiquement QGIS 3 ou 4 et l'interpréteur Python associé.
set -euo pipefail

DEPS="whitebox rasterio geopandas reportlab pyproj"

echo ""
echo "============================================================"
echo "  KarstPro — Installation des dépendances Python"
echo "============================================================"
echo ""

PYTHON_EXE=""
QGIS_VER=""

# ── 1. Environnement conda/mamba actif contenant QGIS ────────────────────────
if command -v python3 &>/dev/null; then
    if python3 -c "import qgis" &>/dev/null 2>&1; then
        PYTHON_EXE="$(command -v python3)"
        QGIS_VER="$(python3 -c "
try:
    from qgis.core import Qgis
    print(Qgis.QGIS_VERSION.split('.')[0])
except Exception:
    print('?')
" 2>/dev/null)"
        echo "[OK] QGIS détecté via Python courant (conda/venv ?)"
        echo "     Version : QGIS ${QGIS_VER}"
        echo "     Python  : ${PYTHON_EXE}"
    fi
fi

# ── 2. QGIS installé via apt (python3-qgis) ───────────────────────────────────
if [ -z "${PYTHON_EXE}" ]; then
    if dpkg -s python3-qgis &>/dev/null 2>&1; then
        PYTHON_EXE="$(command -v python3)"
        # Récupérer la version QGIS via qgis --version si disponible
        if command -v qgis &>/dev/null; then
            RAW="$(qgis --version 2>/dev/null | head -1 || true)"
            QGIS_VER="$(echo "${RAW}" | grep -oP '\d+' | head -1 || echo '?')"
        else
            QGIS_VER="?"
        fi
        echo "[OK] QGIS détecté via paquet système python3-qgis"
        echo "     Version : QGIS ${QGIS_VER}"
        echo "     Python  : ${PYTHON_EXE}"
    fi
fi

# ── 3. QGIS Flatpak (path non standard) ──────────────────────────────────────
if [ -z "${PYTHON_EXE}" ]; then
    FLATPAK_QGIS="/var/lib/flatpak/app/org.qgis.qgis"
    FLATPAK_USR="${HOME}/.local/share/flatpak/app/org.qgis.qgis"
    for FP_DIR in "${FLATPAK_QGIS}" "${FLATPAK_USR}"; do
        if [ -d "${FP_DIR}" ]; then
            echo "[INFO] QGIS Flatpak détecté dans ${FP_DIR}"
            echo "       Le Flatpak utilise son propre Python isolé."
            echo "       Installez les dépendances DEPUIS un terminal Flatpak :"
            echo "         flatpak run --command=bash org.qgis.qgis"
            echo "         pip install ${DEPS}"
            exit 0
        fi
    done
fi

# ── Abandon si QGIS introuvable ───────────────────────────────────────────────
if [ -z "${PYTHON_EXE}" ]; then
    echo "[ERREUR] QGIS introuvable."
    echo ""
    echo "Solutions :"
    echo "  1. Installer QGIS via apt :"
    echo "       sudo apt install qgis python3-qgis"
    echo "  2. Activer l'environnement conda contenant QGIS :"
    echo "       conda activate <nom_env>"
    echo "       puis relancer ce script"
    echo "  3. Installer via le dépôt officiel QGIS :"
    echo "       https://qgis.org/resources/installation-guide/"
    exit 1
fi

echo ""

# ── Choisir la cible pip selon les droits ────────────────────────────────────
# --user si pas root, install directe si conda/venv (pas de --user)
PIP_FLAGS="--upgrade"

# Détecter si on est dans un venv/conda (pas de --user dans ce cas)
if python3 -c "import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)" &>/dev/null 2>&1; then
    echo "[INFO] Environnement virtuel détecté — installation sans --user"
elif [ "${EUID:-$(id -u)}" -eq 0 ]; then
    echo "[INFO] Exécution en root — installation système"
else
    PIP_FLAGS="--user ${PIP_FLAGS}"
    echo "[INFO] Installation dans ~/.local (--user)"
fi

echo ""
echo "Packages : ${DEPS}"
echo ""

# ── Installation ──────────────────────────────────────────────────────────────
# shellcheck disable=SC2086
"${PYTHON_EXE}" -m pip install ${PIP_FLAGS} ${DEPS}

echo ""
echo "============================================================"
echo "  Installation terminée avec succès !"

# Rappel du dossier plugins selon la version QGIS
if [ "${QGIS_VER}" = "4" ]; then
    PLUGIN_DIR="${HOME}/.local/share/QGIS/QGIS4/profiles/default/python/plugins"
else
    PLUGIN_DIR="${HOME}/.local/share/QGIS/QGIS3/profiles/default/python/plugins"
fi

echo "  Dossier plugins QGIS : ${PLUGIN_DIR}"
echo "  Rechargez le plugin KarstPro dans QGIS pour appliquer."
echo "============================================================"
echo ""
