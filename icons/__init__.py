# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
"""Ressources d'icônes KarstPro (charte « Roche »)."""
from pathlib import Path

_ICON_DIR = Path(__file__).resolve().parent

# Symbole vectoriel (net à toute taille) pour les algorithmes et le provider.
SYMBOL_SVG = _ICON_DIR / "karstpro.svg"
# Icône raster du plugin (gestionnaire d'extensions QGIS).
ICON_PNG = _ICON_DIR.parent / "icon.png"


def karst_icon():
    """Retourne un QIcon du symbole KarstPro (SVG, fallback PNG)."""
    try:
        from qgis.PyQt.QtGui import QIcon
    except Exception:
        return None
    if SYMBOL_SVG.exists():
        return QIcon(str(SYMBOL_SVG))
    if ICON_PNG.exists():
        return QIcon(str(ICON_PNG))
    return QIcon()
