# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
# Usage commercial interdit sans autorisation écrite — julien.tournois@gmail.com
# https://polyformproject.org/licenses/noncommercial/1.0.0
from qgis.core import QgsProcessingProvider
from karstpro.algorithms.karst_prep_algorithm import KarstPrepAlgorithm
from karstpro.algorithms.karst_sync_algorithm import KarstSyncAlgorithm
from karstpro.algorithms.karst_export_mll_algorithm import KarstExportMllAlgorithm
from karstpro.algorithms.karst_update_cibles_algorithm import KarstUpdateCiblesAlgorithm


class KarstProProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        self.addAlgorithm(KarstPrepAlgorithm())
        self.addAlgorithm(KarstSyncAlgorithm())
        self.addAlgorithm(KarstExportMllAlgorithm())
        self.addAlgorithm(KarstUpdateCiblesAlgorithm())

    def icon(self):
        from karstpro.icons import karst_icon
        ic = karst_icon()
        return ic if ic is not None else super().icon()

    def id(self):
        return "karstpro"

    def name(self):
        return "KarstPro"

    def longName(self):
        return "KarstPro — Prospection karstique"
