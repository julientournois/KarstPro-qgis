# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
# Usage commercial interdit sans autorisation écrite — julien.tournois@gmail.com
# https://polyformproject.org/licenses/noncommercial/1.0.0
from qgis.core import QgsApplication
from karstpro.karstpro_provider import KarstProProvider


class KarstProPlugin:
    def __init__(self, iface):
        self.provider = None

    def initProcessing(self):
        self.provider = KarstProProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()

    def unload(self):
        QgsApplication.processingRegistry().removeProvider(self.provider)
