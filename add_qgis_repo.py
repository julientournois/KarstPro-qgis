# Copyright (c) 2026 Julien Tournois — PolyForm Noncommercial 1.0
"""Enregistre le dépôt custom KarstPro dans QGIS (mises à jour automatiques).

Ajoute une entrée dans les paramètres QGIS ("Extensions -> Gérer et installer
les extensions -> Paramètres -> Dépôts") pour chaque profil QGIS 3 et/ou 4
détecté, sans avoir à le faire à la main dans l'interface.

⚠ Fermer QGIS avant de lancer ce script : QGIS réécrit ses paramètres à la
fermeture et effacerait sinon la modification.

Doit être exécuté avec un Python ayant PyQt5 ou PyQt6 (celui fourni par QGIS
convient toujours) : voir add_qgis_repo.bat / add_qgis_repo.sh, qui trouvent et
utilisent automatiquement l'interpréteur Python de QGIS.

Usage :
    python add_qgis_repo.py [--dry-run] [--profile NOM] [--ini CHEMIN]
"""
from __future__ import annotations

import argparse
import os
import sys

REPO_NAME = "KarstPro"
REPO_URL = "https://julientournois.github.io/KarstPro-qgis/plugins.xml"


def _qsettings_class():
    """Importe QSettings depuis PyQt5 ou PyQt6, selon ce qui est disponible."""
    try:
        from PyQt5.QtCore import QSettings
        return QSettings
    except ImportError:
        pass
    from PyQt6.QtCore import QSettings
    return QSettings


def _candidate_ini_paths():
    """Chemins plausibles des fichiers de paramètres QGIS (QGIS3.ini / QGIS4.ini),
    tous profils et versions confondus, sur Windows/Linux/macOS."""
    roots = []
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            roots.append(os.path.join(appdata, "QGIS"))
    elif sys.platform == "darwin":
        roots.append(os.path.expanduser(
            "~/Library/Application Support/QGIS"))
    else:
        data_home = os.environ.get(
            "QGIS_DATA_HOME",
            os.path.expanduser("~/.local/share/QGIS"))
        roots.append(data_home)

    paths = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for major in os.listdir(root):  # "QGIS3", "QGIS4", ...
            profiles_dir = os.path.join(root, major, "profiles")
            if not os.path.isdir(profiles_dir):
                continue
            for profile in os.listdir(profiles_dir):
                ini = os.path.join(
                    profiles_dir, profile, "QGIS", f"{major}.ini")
                if os.path.isfile(ini):
                    paths.append((profile, ini))
    return paths


def add_repo(ini_path, dry_run=False):
    """Ajoute/actualise l'entrée du dépôt dans un fichier de paramètres QGIS.

    Toujours actif (`enabled=true`), sans authentification (`authcfg` vide) :
    dépôt public. Idempotent — relancer ne fait que réaffirmer les valeurs.
    """
    QSettings = _qsettings_class()
    group = f"app/plugin_repositories/{REPO_NAME}"
    if dry_run:
        print(f"  [dry-run] {ini_path} : {group}/url = {REPO_URL}")
        return
    s = QSettings(ini_path, QSettings.Format.IniFormat
                  if hasattr(QSettings, "Format") else QSettings.IniFormat)
    s.beginGroup(group)
    s.setValue("url", REPO_URL)
    s.setValue("enabled", True)
    s.setValue("authcfg", "")
    s.endGroup()
    s.sync()
    print(f"  OK : {ini_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                         help="Affiche ce qui serait fait sans rien écrire.")
    parser.add_argument("--profile", default=None,
                         help="Ne traiter que ce profil QGIS (défaut : tous).")
    parser.add_argument("--ini", default=None,
                         help="Chemin explicite d'un fichier .ini (test/avancé), "
                              "ignore la détection automatique.")
    args = parser.parse_args()

    if args.ini:
        targets = [(args.profile or "?", args.ini)]
    else:
        targets = _candidate_ini_paths()
        if args.profile:
            targets = [(p, i) for p, i in targets if p == args.profile]

    if not targets:
        print("Aucun profil QGIS trouvé (QGIS installé ? profil personnalisé ?).")
        print("Utilisez --ini <chemin> pour cibler un fichier précis.")
        sys.exit(1)

    print(f"Dépôt à ajouter : {REPO_NAME} -> {REPO_URL}")
    for profile, ini in targets:
        print(f"Profil « {profile} » :")
        add_repo(ini, dry_run=args.dry_run)
    print("\nTerminé. Relancez QGIS : le dépôt apparaît dans "
          "Extensions -> Gérer et installer les extensions -> Paramètres -> Dépôts.")


if __name__ == "__main__":
    main()
