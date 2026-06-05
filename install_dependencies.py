# Copyright (c) 2026 Julien Tournois — PolyForm Noncommercial License 1.0.0
"""Installe les dépendances Python de KarstPro dans l'interpréteur QGIS courant.

MÉTHODE RECOMMANDÉE (Windows, Linux, macOS — la plus fiable) :

  1. Ouvrir QGIS.
  2. Extensions  >  Console Python.
  3. Dans la console, coller et exécuter :

         import karstpro.install_dependencies

     (ou, si le plugin n'est pas encore actif, ouvrir ce fichier via l'éditeur
      de la console et cliquer « Exécuter le script ».)

Pourquoi cette méthode : le script utilise sys.executable, c'est-à-dire le
Python *de QGIS lui-même*. Il vise donc toujours le bon interpréteur, quelle
que soit la plateforme, sans avoir à deviner un chemin d'installation.

Les scripts install_windows.bat / install_linux.sh font la même chose en
« best-effort » hors de QGIS, mais peuvent échouer à localiser le bon Python :
en cas de doute, utilisez cette console.
"""
import sys
import subprocess
import importlib

# Doit rester synchronisé avec requirements.txt et install_deps.bat/.sh.
PACKAGES = ["geopandas", "rasterio", "reportlab", "whitebox", "pyproj"]

# Modules importés pour vérifier que l'installation a réussi.
_CHECK = ["geopandas", "rasterio", "reportlab", "whitebox", "shapely", "pandas"]


def install(packages=None):
    """Installe les paquets dans le Python courant (celui de QGIS)."""
    packages = packages or PACKAGES
    print("KarstPro — installation des dépendances")
    print(f"  Python ciblé : {sys.executable}")
    cmd = [sys.executable, "-m", "pip", "install"] + packages
    print("  " + " ".join(cmd) + "\n")
    subprocess.check_call(cmd)


def verify():
    """Tente d'importer chaque dépendance ; renvoie True si tout est OK."""
    print("\nVérification des imports :")
    ok = True
    for mod in _CHECK:
        try:
            importlib.import_module(mod)
            print(f"  OK    {mod}")
        except Exception as exc:  # noqa: BLE001 — on veut tout rapporter
            ok = False
            print(f"  ECHEC {mod} : {exc}")
    return ok


def main():
    install()
    ok = verify()
    if ok:
        print("\nTerminé. Redémarrez QGIS pour finir l'activation.")
    else:
        print(
            "\nDes dépendances n'ont pas pu être importées.\n"
            "Relancez ce script, ou installez manuellement depuis la console "
            "Python de QGIS :\n"
            "    import subprocess, sys\n"
            "    subprocess.check_call([sys.executable, '-m', 'pip', 'install', "
            + ", ".join(repr(p) for p in PACKAGES)
            + "])"
        )
    return ok


# S'exécute aussi bien via `import karstpro.install_dependencies` que via
# « Exécuter le script » dans la console Python de QGIS.
main()
