# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
# Usage commercial interdit sans autorisation écrite — julien.tournois@gmail.com
# https://polyformproject.org/licenses/noncommercial/1.0.0
"""Journalisation partagée des algorithmes Processing.

Deux helpers :
  - write_log_header(path, title, parameters) : écrit l'en-tête (versions + params).
  - wrap_feedback(inner, path)                : proxy QgsProcessingFeedback qui
    recopie TOUT le journal (algorithme + modules core) dans le fichier.

Les imports qgis sont différés (QGIS injecte qgis.core avant le chargement des
modules du plugin, mais sys.stderr=None à ce moment-là peut casser certaines
extensions C — on importe donc à l'usage).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


def _versions() -> list[str]:
    """Versions des bibliothèques (best-effort, pour le diagnostic)."""
    out = []
    for label, getter in (
        ("QGIS  ", lambda: __import__("qgis.core", fromlist=["Qgis"]).Qgis.QGIS_VERSION),
        ("Qt    ", lambda: __import__("qgis.PyQt.QtCore", fromlist=["QT_VERSION_STR"]).QT_VERSION_STR),
        ("Python", lambda: __import__("platform").python_version()),
        ("GDAL  ", lambda: __import__("osgeo", fromlist=["gdal"]).gdal.__version__),
    ):
        try:
            out.append(f"{label} : {getter()}")
        except Exception:
            pass
    return out


def write_log_header(path: Path, title: str, parameters: dict | None = None) -> None:
    """Crée/écrase le fichier log avec un en-tête : titre, date, versions, params."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{title}\n")
            f.write(f"Date    : {datetime.now():%Y-%m-%d %H:%M:%S}\n")
            for v in _versions():
                f.write(v + "\n")
            if parameters:
                f.write("\nParamètres en entrée :\n")
                try:
                    for k in sorted(parameters):
                        f.write(f"  {k} = {parameters[k]!r}\n")
                except Exception:
                    pass
            f.write("=" * 60 + "\n\n")
    except Exception:
        pass


def wrap_feedback(inner, path: Path):
    """Retourne un QgsProcessingFeedback qui délègue à `inner` et recopie dans `path`."""
    from qgis.core import QgsProcessingFeedback

    class _LogFeedback(QgsProcessingFeedback):
        def __init__(self, inner, log_path):
            super().__init__()
            self._inner = inner
            self._path = log_path

        def _w(self, msg, prefix="  "):
            try:
                with open(self._path, "a", encoding="utf-8") as fp:
                    fp.write(f"{prefix}{msg}\n")
                    fp.flush()
            except Exception:
                pass

        def pushInfo(self, info):
            self._inner.pushInfo(info)
            self._w(info)

        def pushWarning(self, warning):
            self._inner.pushWarning(warning)
            self._w(warning, "⚠ ")

        def pushCommandInfo(self, info):
            self._inner.pushCommandInfo(info)
            self._w(info)

        def pushDebugInfo(self, info):
            self._inner.pushDebugInfo(info)
            self._w(info, "[dbg] ")

        def pushConsoleInfo(self, info):
            try:
                self._inner.pushConsoleInfo(info)
            except Exception:
                pass
            self._w(info)

        def reportError(self, error, fatalError=False):
            self._inner.reportError(error, fatalError)
            self._w(error, "✗ ")

        def setProgress(self, p):
            self._inner.setProgress(p)

        def progress(self):
            return self._inner.progress()

        def isCanceled(self):
            return self._inner.isCanceled()

    return _LogFeedback(inner, path)


def doc_url() -> str:
    """URL d'aide (file://) vers le PDF de documentation, pour helpUrl().

    Cherche KarstPro_Documentation.pdf dans le dossier du plugin (karstpro/)
    puis à la racine du dépôt (cas dev). Retourne '' si introuvable.
    """
    here = Path(__file__).resolve().parent.parent  # .../karstpro
    for cand in (here / "KarstPro_Documentation.pdf",
                 here.parent / "KarstPro_Documentation.pdf"):
        if cand.exists():
            return cand.as_uri()
    return ""
