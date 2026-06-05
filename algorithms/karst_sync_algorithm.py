# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
# Usage commercial interdit sans autorisation écrite — julien.tournois@gmail.com
# https://polyformproject.org/licenses/noncommercial/1.0.0
from datetime import date
from pathlib import Path
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterVectorLayer,
    QgsProcessing,
    QgsProcessingContext,
    QgsProcessingFeedback,
)

# NOTE: geopandas and karstpro.core.* imports are deferred to inside
# processAlgorithm() to avoid the sys.stderr=None crash at QGIS plugin load.


class KarstSyncAlgorithm(QgsProcessingAlgorithm):
    """Met à jour l'inventaire « Inventaire Cavités » avec les cavités saisies
    sur le terrain dans QField, puis génère un rapport PDF de la sortie.

    Workflow : saisie téléphone (couche cavités) → sync du projet bureau via
    QFieldSync → CET outil pousse les nouvelles cavités dans l'inventaire.
    """

    QFIELD_GPKG = "QFIELD_GPKG"
    INVENTORY = "INVENTORY"
    DEDUP_THRESHOLD = "DEDUP_THRESHOLD"
    OUTPUT_DIR = "OUTPUT_DIR"

    def name(self):
        return "karst_sync"

    def displayName(self):
        return "KarstPro — Synchroniser le retour terrain"

    def group(self):
        return "KarstPro"

    def groupId(self):
        return "karstpro"

    def createInstance(self):
        return KarstSyncAlgorithm()

    def helpUrl(self):
        from karstpro.core.log_feedback import doc_url
        return doc_url()

    def icon(self):
        from karstpro.icons import karst_icon
        ic = karst_icon()
        return ic if ic is not None else super().icon()

    def shortHelpString(self):
        return (
            "Pousse les cavités saisies sur le terrain (couche « cavites » du "
            "projet QField) dans l'inventaire « Inventaire Cavités ».\n\n"
            "Pour chaque nouvelle cavité : référence auto-générée si vide, "
            "localisation administrative (commune/INSEE/CP/département) résolue "
            "par géocodage inverse. Les cavités déjà présentes dans l'inventaire "
            "(même référence ou trop proches) sont ignorées.\n\n"
            "Marche à suivre :\n"
            "1. Sur le bureau, synchronise le projet QField (QFieldSync → "
            "rapatrier les données du cloud).\n"
            "2. Lance cet outil : champ 1 = le .gpkg du projet QField rapatrié, "
            "champ 2 = ta couche inventaire « Inventaire Cavités ».\n\n"
            "Un rapport PDF de la sortie est généré (une fiche par cavité)."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile(
            self.QFIELD_GPKG,
            "1. GeoPackage du projet QField (retour terrain rapatrié du cloud)",
            extension="gpkg"))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INVENTORY,
            "2. Couche inventaire à mettre à jour « Inventaire Cavités » "
            "(chargée dans le projet, ou « … » pour parcourir son .gpkg)",
            types=[QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterNumber(
            self.DEDUP_THRESHOLD,
            "Distance de regroupement GPS (m) — deux points plus proches sont "
            "considérés comme la même cavité (évite les doublons)",
            defaultValue=10.0, minValue=1.0, maxValue=100.0))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUTPUT_DIR,
            "Dossier du rapport PDF (optionnel — par défaut : dossier du projet "
            "QField, sous RapportSortie/JJ-MM-AAAA)",
            optional=True, createByDefault=False))

    def processAlgorithm(self, parameters, context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        import geopandas as gpd
        from karstpro.core.sync import deduplicate_by_proximity
        from karstpro.core.report import generate_report
        from qgis.core import QgsProcessingException

        qfield_gpkg = Path(self.parameterAsFile(parameters, self.QFIELD_GPKG, context))
        inv_layer = self.parameterAsVectorLayer(parameters, self.INVENTORY, context)
        threshold = self.parameterAsDouble(parameters, self.DEDUP_THRESHOLD, context)
        output_str = self.parameterAsString(parameters, self.OUTPUT_DIR, context)

        if not qfield_gpkg.exists():
            raise QgsProcessingException(
                f"GeoPackage QField introuvable : {qfield_gpkg}.")
        if inv_layer is None:
            raise QgsProcessingException(
                "Aucune couche inventaire sélectionnée. Choisis « Inventaire "
                "Cavités » (couche chargée ou via « … »).")

        # Dossier rapport : explicite, sinon dossier du projet QField.
        if output_str:
            report_dir = Path(output_str)
        else:
            report_dir = (qfield_gpkg.parent / "RapportSortie"
                          / date.today().strftime("%d-%m-%Y"))
        report_dir.mkdir(parents=True, exist_ok=True)

        feedback.pushInfo("Lecture des cavités saisies sur le terrain...")
        new_cav = gpd.read_file(qfield_gpkg, layer="cavites")
        new_cav = deduplicate_by_proximity(new_cav, threshold_m=threshold)
        feedback.pushInfo(f"  {len(new_cav)} cavité(s) dans le retour terrain.")

        promoted, skipped = self._update_inventory(
            new_cav, inv_layer, qfield_gpkg, threshold, feedback)

        feedback.pushInfo("Génération du rapport PDF...")
        secteur = qfield_gpkg.stem
        report_path = report_dir / f"rapport_{secteur}_{date.today():%d-%m-%Y}.pdf"
        generate_report(secteur, new_cav, report_path)

        feedback.pushInfo(
            f"Inventaire mis à jour : {promoted} cavité(s) ajoutée(s), "
            f"{skipped} déjà présente(s) (ignorées).")
        feedback.pushInfo(f"Rapport : {report_path}")
        return {self.OUTPUT_DIR: str(report_dir)}

    def _update_inventory(self, new_cav, inv_layer, qfield_gpkg, threshold,
                          feedback):
        """Ajoute les cavités terrain absentes à la couche inventaire (édition
        par le fournisseur QGIS : pas de verrou fichier, rafraîchissement direct
        si la couche est chargée). Retourne (n_ajoutées, n_ignorées)."""
        import re
        from qgis.core import QgsProcessingException

        if new_cav.empty:
            feedback.pushWarning("Aucune cavité à ajouter.")
            return 0, 0

        # Garde-fou 1 : ne pas viser la couche tampon « cavites » elle-même.
        src = inv_layer.source() or ""
        m = re.search(r"layername=([^|]+)", src)
        tbl = (m.group(1) if m else "").strip().lower()
        if tbl == "cavites" or inv_layer.name().strip().lower() == "cavites":
            raise QgsProcessingException(
                "Tu as sélectionné la couche de saisie « cavites » comme cible. "
                "Choisis la couche SÉPARÉE « Inventaire Cavités », pas la couche "
                "terrain.")
        # Garde-fou 2 : ne pas viser le gpkg QField (retour brut).
        try:
            same_file = (src and Path(src.split("|")[0]).resolve()
                         == qfield_gpkg.resolve())
        except OSError:
            same_file = False
        if same_file:
            raise QgsProcessingException(
                "La couche inventaire pointe le GeoPackage QField (retour "
                "terrain). Sélectionne ton fichier « Inventaire Cavités ».")
        # Garde-fou 3 : schéma cavité minimal.
        missing = [f for f in ("name", "reference")
                   if inv_layer.fields().indexOf(f) < 0]
        if missing:
            raise QgsProcessingException(
                f"La couche « {inv_layer.name()} » n'a pas le schéma inventaire "
                f"(champ(s) manquant(s) {missing}). Sélectionne la couche "
                "« Inventaire Cavités » de Karst Entry.")

        feedback.pushInfo(
            f"Mise à jour de « {inv_layer.name()} » "
            "(référence auto + commune géocodée pour les nouvelles).")
        return self._add_to_inventory_layer(new_cav, inv_layer, threshold, feedback)

    def _add_to_inventory_layer(self, new_cav, inv_layer, threshold, feedback):
        import pandas as pd
        import geopandas as gpd
        from shapely import wkt as _wkt
        from karstpro.core.sync import (
            select_promotable, build_promotion_gdf, make_cached_geocoder,
        )
        from qgis.core import QgsFeature, QgsGeometry

        # Inventaire existant → GDF léger (géométrie + reference) pour le
        # dédoublonnage, lu depuis le fournisseur (couche vivante).
        inv_fields = inv_layer.fields()
        has_ref = inv_fields.indexOf("reference") >= 0
        inv_geoms, inv_refs = [], []
        for f in inv_layer.getFeatures():
            g = f.geometry()
            inv_geoms.append(g.asWkt() if g and not g.isEmpty() else None)
            inv_refs.append(f["reference"] if has_ref else None)
        inv_gdf = gpd.GeoDataFrame(
            {"reference": inv_refs,
             "geometry": [_wkt.loads(w) if w else None for w in inv_geoms]},
            crs="EPSG:2154")

        to_add, skipped = select_promotable(new_cav, inv_gdf, threshold)
        if not to_add:
            return 0, len(skipped)

        inv_crs_id = (inv_layer.crs().authid()
                      if inv_layer.crs().isValid() else "EPSG:2154")
        promo = build_promotion_gdf(
            new_cav, to_add, target_crs=inv_crs_id,
            geocoder=make_cached_geocoder(),
            ref_start=inv_layer.featureCount() + 1)

        feats = []
        for _, prow in promo.iterrows():
            feat = QgsFeature(inv_fields)
            for col in promo.columns:
                if col == "geometry":
                    continue
                fi = inv_fields.indexOf(col)
                if fi < 0:
                    continue
                val = prow[col]
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    continue
                feat.setAttribute(fi, str(val))
            geom = prow.geometry
            feat.setGeometry(
                QgsGeometry.fromWkt(geom.wkt) if geom is not None else QgsGeometry())
            feats.append(feat)

        ok, _ = inv_layer.dataProvider().addFeatures(feats)
        if not ok:
            from qgis.core import QgsProcessingException
            raise QgsProcessingException(
                "Échec de l'ajout à l'inventaire (couche non éditable ou "
                "verrouillée ?). Vérifie qu'elle n'est pas en cours d'édition.")
        inv_layer.updateExtents()
        inv_layer.triggerRepaint()
        return len(to_add), len(skipped)
