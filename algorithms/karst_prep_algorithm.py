# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
# Usage commercial interdit sans autorisation écrite — julien.tournois@gmail.com
# https://polyformproject.org/licenses/noncommercial/1.0.0
from __future__ import annotations  # must be first non-comment statement

from pathlib import Path
from typing import TYPE_CHECKING

# NOTE: qgis.core imports are at module level because QGIS injects these
# before loading plugin modules. All karstpro.core.* and heavy third-party
# imports (numpy, geopandas, rasterio) are deferred to inside
# processAlgorithm() — QGIS sets sys.stderr=None during plugin load which
# crashes C-extensions that emit deprecation warnings.
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterString,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterNumber,
    QgsProcessingParameterBoolean,
    QgsProcessing,
)

if TYPE_CHECKING:
    import geopandas as gpd


class KarstPrepAlgorithm(QgsProcessingAlgorithm):
    EXTENT = "EXTENT"
    TOPO_FILE = "TOPO_FILE"
    SCORING_CONFIG = "SCORING_CONFIG"
    OUTPUT_DIR = "OUTPUT_DIR"
    SECTEUR_NAME = "SECTEUR_NAME"
    CAVITES_CONNUES = "CAVITES_CONNUES"
    TRACAGES = "TRACAGES"
    MNT_FILES = "MNT_FILES"
    GEO_LOCAL = "GEO_LOCAL"
    CONTOUR_INTERVAL = "CONTOUR_INTERVAL"
    INCLUDE_MNT_HILLSHADE = "INCLUDE_MNT_HILLSHADE"

    def name(self):
        return "karst_prep"

    def displayName(self):
        return "KarstPro — Préparer une sortie"

    def group(self):
        return "KarstPro"

    def groupId(self):
        return "karstpro"

    def createInstance(self):
        return KarstPrepAlgorithm()

    def helpUrl(self):
        from karstpro.core.log_feedback import doc_url
        return doc_url()

    def icon(self):
        from karstpro.icons import karst_icon
        ic = karst_icon()
        return ic if ic is not None else super().icon()

    def _add_advanced(self, param):
        """Place le paramètre dans la section repliable « Paramètres avancés »."""
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

    def initAlgorithm(self, config=None):
        # ── Paramètres requis (toujours visibles) ──────────────────────────
        self.addParameter(QgsProcessingParameterString(
            self.SECTEUR_NAME,
            "Nom du secteur (laisser vide = commune au centre de l'emprise, auto)",
            optional=True))
        self.addParameter(QgsProcessingParameterExtent(
            self.EXTENT, "Zone d'étude (bbox)"))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUTPUT_DIR, "Dossier de sortie"))

        # ── Paramètres optionnels (section « avancés », repliée par défaut) ─
        self._add_advanced(QgsProcessingParameterFile(
            self.TOPO_FILE, "Topo réseau existant (.shp ou .kml)", optional=True))
        self._add_advanced(QgsProcessingParameterFile(
            self.SCORING_CONFIG, "Config scoring JSON", optional=True))
        # GeoPackage inventaire (cavités connues) — fichier partagé Karst Entry.
        # Doit contenir la couche « Inventaire Cavités » / cavites_connues. Il
        # est ajouté au projet en lecture seule (NON copié dans le package).
        self._add_advanced(QgsProcessingParameterFile(
            self.CAVITES_CONNUES,
            "GeoPackage inventaire cavités (.gpkg avec « Inventaire Cavités »)",
            optional=True, extension="gpkg",
        ))
        # GeoPackage traçages — doit contenir « Inventaire Traçages » / tracages.
        self._add_advanced(QgsProcessingParameterFile(
            self.TRACAGES,
            "GeoPackage traçages (.gpkg avec « Inventaire Traçages »)",
            optional=True, extension="gpkg",
        ))
        self._add_advanced(QgsProcessingParameterMultipleLayers(
            self.MNT_FILES,
            "MNT IGN pré-téléchargé(s) — dernier recours (LHD_FXX_…_MNT_….tif)",
            layerType=QgsProcessing.TypeRaster,
            optional=True,
        ))
        self._add_advanced(QgsProcessingParameterFile(
            self.GEO_LOCAL,
            "Géologie locale BD Charm-50 1/50 000 (optionnel — GPKG ou shapefile)",
            optional=True,
            extension="",  # accepte .gpkg et .shp
        ))
        self._add_advanced(QgsProcessingParameterNumber(
            self.CONTOUR_INTERVAL,
            "Courbes de niveau — équidistance en m (0 = désactivé ; "
            "maîtresses en gras + cote tous les 10 m)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=5.0,
            minValue=0.0,
            optional=True,
        ))
        # Ombrage MNT : décocher l'exclut du projet — et donc du paquet
        # QFieldCloud (qui copie tous les rasters et ignore le flag remove).
        # Décocher pour un projet cloud léger ; cocher pour l'analyse bureau.
        # Paramètre de base (visible par défaut, hors section avancée).
        self.addParameter(QgsProcessingParameterBoolean(
            self.INCLUDE_MNT_HILLSHADE,
            "Inclure l'ombrage MNT dans le projet (décocher pour alléger "
            "QFieldCloud — le MNT n'apparaîtra ni au bureau ni sur le terrain)",
            defaultValue=True,
        ))

    # ── Helpers UI ────────────────────────────────────────────────────────────

    def _log(self, feedback: "QgsProcessingFeedback", msg: str,
             log_file: "Path | None" = None, warn: bool = False) -> None:
        """pushInfo/pushWarning (le proxy feedback recopie dans le fichier) + processEvents."""
        from qgis.core import QgsApplication
        if warn:
            feedback.pushWarning(msg)
        else:
            feedback.pushInfo(msg)
        # Laisser Qt traiter ses événements (repaint log, barre de progression…)
        QgsApplication.processEvents()

    def _step(self, feedback: "QgsProcessingFeedback", msg: str,
              progress: int, log_file: "Path | None" = None) -> None:
        """Checkpoint : titre de section + progression + processEvents."""
        from qgis.core import QgsApplication
        feedback.setProgress(progress)
        feedback.pushInfo(f"\n{'─'*60}\n{msg}\n{'─'*60}")
        QgsApplication.processEvents()

    @staticmethod
    def _sanitize_name(s: str) -> str:
        """Rend un nom de commune sûr pour un nom de fichier/couche : ASCII,
        sans espaces ni apostrophes. Ex. « L'Île-d'Elle » → « L-Ile-d-Elle »."""
        import re
        import unicodedata
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
        s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
        return s or "Secteur"

    def _auto_secteur_name(self, extent, extent_crs, feedback) -> str:
        """Déduit le nom du secteur de la commune au centre de l'emprise
        (géocodage inverse geo.api.gouv.fr). Repli « Secteur » si échec réseau.
        """
        commune = ""
        try:
            from qgis.core import (
                QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject,
            )
            from karstpro.core.sync import _fetch_commune_with_contour
            center = extent.center()  # QgsPointXY dans extent_crs
            wgs = QgsCoordinateReferenceSystem("EPSG:4326")
            if extent_crs.isValid() and extent_crs != wgs:
                tr = QgsCoordinateTransform(extent_crs, wgs, QgsProject.instance())
                center = tr.transform(center)
            admin, _ = _fetch_commune_with_contour(center.y(), center.x())
            commune = (admin or {}).get("commune", "").strip()
        except Exception as exc:
            feedback.pushWarning(f"Géocodage commune échoué : {exc}")
        if commune:
            name = self._sanitize_name(commune)
            feedback.pushInfo(
                f"Nom du secteur auto : « {name} » (commune au centre de l'emprise).")
            return name
        feedback.pushWarning(
            "Commune non résolue (réseau ?) — nom de secteur par défaut "
            "« Secteur ». Renomme le projet si besoin.")
        return "Secteur"

    def processAlgorithm(self, parameters, context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        # Lazy imports — deferred until algorithm actually runs (sys.stderr is
        # properly set by then, so C-extension deprecation warnings are safe).
        import shutil
        import geopandas as gpd
        from karstpro.core.lidar import (
            bbox_to_ign_tiles, download_lidar_tiles, generate_mnt,
            detect_dolines, compute_hydrology, compute_bassin_versant,
        )
        from karstpro.core.geology import fetch_brgm_geology, load_local_geology, fetch_geology_auto, check_bdlisa_karst, fetch_georisques_cavites
        from karstpro.core.topo import load_topo
        from karstpro.core.scoring import compute_scores, load_config, compute_cavites_connues_proximity
        from karstpro.core.qfield import package_qfield_project, write_cibles_from_scored_dolines
        from karstpro.core.gpkg import CAVITES_SCHEMA

        from qgis.core import (
            QgsCoordinateReferenceSystem,
            QgsCoordinateTransform,
            QgsProject,
        )

        from datetime import datetime
        name = self.parameterAsString(parameters, self.SECTEUR_NAME, context)
        extent = self.parameterAsExtent(parameters, self.EXTENT, context)
        # GeoPackage inventaire (cavités connues) et traçages : on récupère le
        # chemin + la couche (détectée par schéma). Ils ne sont PAS copiés : ils
        # sont lus pour la proximité (cavités) et référencés en lecture seule.
        from karstpro.core.sync import find_inventory_layer, find_tracages_layer
        cc_gpkg_str = self.parameterAsFile(parameters, self.CAVITES_CONNUES, context)
        tr_gpkg_str = self.parameterAsFile(parameters, self.TRACAGES, context)
        cavites_connues_gpkg = Path(cc_gpkg_str) if cc_gpkg_str else None
        tracages_gpkg = Path(tr_gpkg_str) if tr_gpkg_str else None
        cavites_connues_layer_name = None
        tracages_layer_name = None
        if cavites_connues_gpkg is not None and cavites_connues_gpkg.exists():
            cavites_connues_layer_name = find_inventory_layer(cavites_connues_gpkg)
            if cavites_connues_layer_name is None:
                feedback.pushWarning(
                    f"« {cavites_connues_gpkg.name} » ne contient pas de couche "
                    "inventaire valide (name/reference) — ignoré.")
        if tracages_gpkg is not None and tracages_gpkg.exists():
            tracages_layer_name = find_tracages_layer(tracages_gpkg)
            if tracages_layer_name is None:
                feedback.pushWarning(
                    f"« {tracages_gpkg.name} » ne contient pas de couche traçages "
                    "valide (colorant/point_injection) — ignoré.")
        mnt_layers = self.parameterAsLayerList(parameters, self.MNT_FILES, context)
        geo_local_file = self.parameterAsFile(parameters, self.GEO_LOCAL, context)
        extent_crs = self.parameterAsExtentCrs(parameters, self.EXTENT, context)
        topo_file = self.parameterAsFile(parameters, self.TOPO_FILE, context)
        config_file = self.parameterAsFile(parameters, self.SCORING_CONFIG, context)
        output_dir = Path(self.parameterAsString(parameters, self.OUTPUT_DIR, context))
        output_dir.mkdir(parents=True, exist_ok=True)

        # Nom du secteur auto : si vide, commune au centre de l'emprise.
        if not name.strip():
            name = self._auto_secteur_name(extent, extent_crs, feedback)

        # Log fichier — persiste même si la boîte de dialogue se ferme
        log_file = output_dir / f"karstpro_prep_{name}_{datetime.now():%Y%m%d_%H%M%S}.log"
        from karstpro.core.log_feedback import write_log_header, wrap_feedback
        write_log_header(log_file, f"KarstPro — Préparer une sortie ({name})", parameters)
        feedback = wrap_feedback(feedback, log_file)
        _t0 = datetime.now()

        # Reproject extent to Lambert-93 (EPSG:2154) — QGIS returns the extent
        # in the project CRS which may be WGS84 degrees or anything else.
        l93 = QgsCoordinateReferenceSystem("EPSG:2154")
        if extent_crs.isValid() and extent_crs.authid() != "EPSG:2154":
            transform = QgsCoordinateTransform(extent_crs, l93, QgsProject.instance())
            extent = transform.transformBoundingBox(extent)
            feedback.pushInfo(
                f"Bbox reprojetée {extent_crs.authid()} → EPSG:2154 : "
                f"({extent.xMinimum():.0f}, {extent.yMinimum():.0f}, "
                f"{extent.xMaximum():.0f}, {extent.yMaximum():.0f})"
            )
        else:
            feedback.pushInfo(
                f"Bbox L93 : ({extent.xMinimum():.0f}, {extent.yMinimum():.0f}, "
                f"{extent.xMaximum():.0f}, {extent.yMaximum():.0f})"
            )

        bbox = (
            extent.xMinimum(), extent.yMinimum(),
            extent.xMaximum(), extent.yMaximum(),
        )

        # --- Guard clause : vérification BDLISA (fail-open, non bloquant) ---
        self._step(feedback, "Vérification zone karstique BDLISA", 3, log_file)
        try:
            if not check_bdlisa_karst(bbox):
                feedback.pushWarning(
                    "⚠ La zone sélectionnée ne semble pas intersecte une entité "
                    "karstique référencée dans BDLISA. Vérifiez que votre secteur "
                    "est bien en contexte karstique avant de continuer. "
                    "(Le traitement continue normalement.)"
                )
            else:
                feedback.pushInfo("✓ Zone karstique BDLISA confirmée.")
        except Exception as exc:
            feedback.pushInfo(f"BDLISA non disponible ({exc}) — vérification ignorée.")

        work_dir = output_dir / "lidar_work"
        work_dir.mkdir(parents=True, exist_ok=True)

        mnt_path = work_dir / "mnt.tif"
        laz_dir = work_dir / "laz"

        # --- Step 1 & 2 : LIDAR download + MNT generation ---
        # Court-circuit : si des MNT pré-téléchargés sont fournis (TIF IGN),
        # on les mosaïque directement dans work_dir/mnt.tif sans passer par les LAZ.
        self._step(feedback, "Étape 1-2 — LiDAR / MNT", 5, log_file)
        if mnt_layers:
            mnt_src_paths = [Path(lyr.source()) for lyr in mnt_layers]
            feedback.pushInfo(
                f"Mode MNT manuel : {len(mnt_src_paths)} dalle(s) IGN fournies — "
                "étapes téléchargement LAZ et PDAL ignorées."
            )
            feedback.setProgress(20)
            if not mnt_path.exists() or mnt_path.stat().st_size == 0:
                if len(mnt_src_paths) == 1:
                    shutil.copy2(mnt_src_paths[0], mnt_path)
                    feedback.pushInfo(f"  MNT copié : {mnt_src_paths[0].name}")
                else:
                    import rasterio
                    from rasterio.merge import merge as rio_merge
                    datasets = [rasterio.open(p) for p in mnt_src_paths]
                    mosaic, out_transform = rio_merge(datasets)
                    out_meta = datasets[0].meta.copy()
                    out_meta.update({
                        "driver": "GTiff",
                        "height": mosaic.shape[1],
                        "width": mosaic.shape[2],
                        "transform": out_transform,
                        "compress": "lzw",
                    })
                    with rasterio.open(mnt_path, "w", **out_meta) as dest:
                        dest.write(mosaic)
                    for ds in datasets:
                        ds.close()
                    feedback.pushInfo(
                        f"  Mosaïque de {len(mnt_src_paths)} dalles → {mnt_path.name}"
                    )
            else:
                feedback.pushInfo("MNT déjà présent — étape ignorée.")
        else:
            feedback.pushInfo("Téléchargement des dalles LIDAR HD IGN...")
            tiles = bbox_to_ign_tiles(bbox)
            feedback.pushInfo(f"  {len(tiles)} dalle(s) — téléchargement parallèle (3 threads)...")

            laz_dir.mkdir(parents=True, exist_ok=True)
            links_path = laz_dir / "dalles_a_telecharger.txt"
            with open(links_path, "w", encoding="utf-8") as f:
                f.write(f"# Dalles LiDAR HD IGN — {name}\n")
                f.write(f"# {len(tiles)} dalle(s) — déposer les .copc.laz dans ce dossier\n")
                f.write(f"# Dossier : {laz_dir}\n\n")
                for tile in tiles:
                    f.write(f"{tile['url']}\n")
            feedback.pushInfo(f"  Liens de téléchargement manuel : {links_path}")

            laz_files = download_lidar_tiles(tiles, laz_dir, feedback=feedback)

            feedback.setProgress(20)
            if mnt_path.exists() and mnt_path.stat().st_size > 0:
                feedback.pushInfo("MNT déjà généré — étape ignorée.")
            else:
                feedback.pushInfo("Génération du MNT (cela peut prendre plus de 30 min selon la surface et la puissance de calcul)...")
                generate_mnt(laz_files, mnt_path)

        # --- Step 3 : Dolines (skipped if intermediate file exists) ---
        self._step(feedback, "Étape 3 — Détection des dolines", 35, log_file)
        mnt_filled = work_dir / "mnt_filled.tif"
        if mnt_filled.exists() and mnt_filled.stat().st_size > 0:
            feedback.pushInfo("Dolines déjà calculées — étape ignorée.")
            dolines_path = work_dir / "dolines.gpkg"
            dolines = gpd.read_file(dolines_path) if dolines_path.exists() else detect_dolines(mnt_path, work_dir)
        else:
            feedback.pushInfo("Détection des dolines...")
            dolines = detect_dolines(mnt_path, work_dir)
            # Cache dolines to disk for potential restart
            if not dolines.empty:
                dolines.to_file(work_dir / "dolines.gpkg", driver="GPKG")

        # --- Step 4 : Hydrology (skipped if intermediate files exist) ---
        self._step(feedback, "Étape 4 — Hydrologie", 50, log_file)
        streams_path = work_dir / "streams.tif"
        if streams_path.exists() and streams_path.stat().st_size > 0:
            feedback.pushInfo("Hydrologie déjà calculée — étape ignorée.")
            reseau_path = work_dir / "reseau.gpkg"
            absorb_path = work_dir / "absorptions.gpkg"
            if reseau_path.exists() and absorb_path.exists():
                reseau = gpd.read_file(reseau_path)
                absorptions = gpd.read_file(absorb_path)
            else:
                reseau, absorptions = compute_hydrology(mnt_path, work_dir)
        else:
            feedback.pushInfo("Calcul de l'hydrologie...")
            reseau, absorptions = compute_hydrology(mnt_path, work_dir)
            # Cache to disk
            if not reseau.empty:
                reseau.to_file(work_dir / "reseau.gpkg", driver="GPKG")
            if not absorptions.empty:
                absorptions.to_file(work_dir / "absorptions.gpkg", driver="GPKG")

        # --- Step 4b : Bassin versant amont (flow accumulation D8) -------------
        flow_acc_path = work_dir / "flow_acc.tif"
        if not dolines.empty and flow_acc_path.exists():
            feedback.pushInfo("Calcul des bassins versants amont (flow accumulation)...")
            try:
                dolines = compute_bassin_versant(dolines, flow_acc_path)
                n_pertes       = (dolines["type_doline"] == "perte").sum()
                n_doline_perte = (dolines["type_doline"] == "doline-perte").sum()
                feedback.pushInfo(
                    f"  Types détectés : {n_pertes} perte(s), "
                    f"{n_doline_perte} doline-perte(s), "
                    f"{len(dolines) - n_pertes - n_doline_perte} doline(s) simples."
                )
                self._log(feedback, f"Bassins versants : {n_pertes} pertes, {n_doline_perte} dolines-pertes", log_file=log_file)
            except Exception as exc:
                feedback.pushWarning(f"Bassin versant ignoré : {exc}")
                dolines["bassin_versant_m2"] = float("nan")
                dolines["type_doline"] = "doline"
        elif not dolines.empty:
            feedback.pushWarning(
                "flow_acc.tif absent — bassin versant non calculé. "
                "Relancer la préparation complète pour obtenir la classification perte/doline-perte."
            )
            dolines["bassin_versant_m2"] = float("nan")
            dolines["type_doline"] = "doline"

        # --- Step 4c : Cold air pooling index + pente bord (MNT 1 m) --------
        if not dolines.empty:
            feedback.setProgress(53)
            feedback.pushInfo("Calcul de l'indice de piégeage d'air froid (MNT 1 m)...")
            try:
                from karstpro.core.cold_air import compute_cold_air_index, compute_slope_max_bord
                dolines = compute_cold_air_index(dolines, mnt_path, feedback)
            except Exception as exc:
                feedback.pushWarning(f"Cold air index ignoré : {exc}")
                dolines = dolines.copy()
                dolines["cold_air_index"] = float("nan")

            feedback.setProgress(57)
            feedback.pushInfo("Calcul de la pente maximale des bords de dolines...")
            try:
                dolines = compute_slope_max_bord(dolines, mnt_path, feedback=feedback)
            except Exception as exc:
                feedback.pushWarning(f"Pente bord ignorée : {exc}")
                dolines["pente_max_bord"] = float("nan")

        self._step(feedback, "Étape 5 — Géologie", 60, log_file)
        if geo_local_file:
            # Fichier géologie fourni manuellement — priorité absolue
            feedback.pushInfo(
                f"Import géologie locale BD Charm-50 1/50 000 : {geo_local_file}"
            )
            geology = load_local_geology(geo_local_file, bbox)
            if geology.empty:
                feedback.pushWarning(
                    "Géologie locale vide dans la bbox — fallback WFS BRGM 1/1 000 000."
                )
                geology = fetch_brgm_geology(bbox)
            else:
                descr_col = next(
                    (c for c in geology.columns if c.upper() == "DESCR"), None
                )
                feedback.pushInfo(
                    f"Geologie locale : {len(geology)} formation(s) calcaires dans la bbox"
                    + (f" (ex: {geology[descr_col].iloc[0][:60]})" if descr_col else "")
                )
        else:
            # Auto : BD Charm-50 cache local si dispo, sinon WFS BRGM
            feedback.pushInfo("Import geologie — BD Charm-50 1/50 000 (cache auto)...")
            geology = fetch_geology_auto(bbox, feedback=feedback)

        feedback.pushInfo("Import cavités Géorisques BRGM...")
        try:
            cavites_georisques = fetch_georisques_cavites(bbox)
            if cavites_georisques.empty:
                feedback.pushInfo(
                    "Géorisques : aucune cavité référencée dans la zone "
                    "(normal dans les karsts sous couverture peu inventoriés)."
                )
            else:
                feedback.pushInfo(
                    f"Géorisques : {len(cavites_georisques)} cavité(s) trouvée(s)."
                )
        except Exception as exc:
            feedback.pushWarning(f"Géorisques ignoré : {exc}")
            cavites_georisques = None

        topo = None
        if topo_file:
            feedback.pushInfo(f"Import topo réseau : {topo_file}")
            topo = load_topo(Path(topo_file))
            if topo.passages.empty:
                feedback.pushInfo("⚠ Topo chargée mais passages vides — vérifiez le format du fichier (LineString attendu).")
            else:
                feedback.pushInfo(
                    f"Topo OK : {len(topo.passages)} segment(s), CRS={topo.passages.crs.to_epsg()}"
                )
                if not dolines.empty:
                    sample_centroid = dolines.geometry.iloc[0].centroid
                    min_dist = topo.passages.geometry.distance(sample_centroid).min()
                    feedback.pushInfo(f"Distance doline[0] → réseau : {min_dist:.0f} m")
        else:
            feedback.pushInfo("Pas de topo fournie — score positionnel désactivé.")

        self._step(feedback, "Étape 6 — Scoring", 70, log_file)
        config = load_config(Path(config_file)) if config_file else None
        scored_dolines = compute_scores(
            dolines, geology, topo=topo, config=config
        )

        # --- Step 6b : Cavités connues — flag proximité (informatif, hors score) ---
        # Sources fusionnées pour le calcul : couche utilisateur + Géorisques BRGM.
        # Les deux sont normalisées sur le schéma (name, type, reference) avant fusion.
        cavites_connues_gdf = None
        if cavites_connues_layer_name is not None:
            feedback.pushInfo("Chargement des cavités connues (proximité)...")
            try:
                cavites_connues_gdf = gpd.read_file(
                    cavites_connues_gpkg, layer=cavites_connues_layer_name)
                # Forcer EPSG:2154 — l'inventaire peut être en WGS84
                if cavites_connues_gdf.crs is None:
                    cavites_connues_gdf = cavites_connues_gdf.set_crs("EPSG:2154")
                elif cavites_connues_gdf.crs.to_epsg() != 2154:
                    cavites_connues_gdf = cavites_connues_gdf.to_crs("EPSG:2154")
                feedback.pushInfo(f"  {len(cavites_connues_gdf)} cavité(s) connue(s) chargée(s).")
            except Exception as exc:
                feedback.pushWarning(f"Cavités connues ignorées : {exc}")

        # Traçages : NON copiés. Référencés en lecture seule (cf. external_layers).
        # Plus de chargement gdf ici — le MLL les lira depuis le gpkg traçages.

        # Normaliser et fusionner les cavités Géorisques avec les cavités utilisateur
        cavites_pour_proximite = _merge_cavites_sources(cavites_connues_gdf, cavites_georisques)

        if not cavites_pour_proximite.empty:
            scored_dolines = compute_cavites_connues_proximity(
                scored_dolines, cavites_pour_proximite, radius_m=20.0
            )
            n_proches = scored_dolines["cavite_connue_proche"].sum()
            feedback.pushInfo(
                f"  {n_proches} doline(s) à moins de 20 m d'une cavité connue "
                f"— marquées cavite_connue_proche=True "
                f"(sources : utilisateur + Géorisques BRGM)."
            )
        else:
            # Colonnes vides pour cohérence du schéma GPKG
            scored_dolines = compute_cavites_connues_proximity(scored_dolines, None)

        self._step(feedback, "Étape 7 — Packaging QField / GPKG", 85, log_file)
        cav_empty = gpd.GeoDataFrame(
            columns=list(CAVITES_SCHEMA.keys()) + ["geometry"], crs="EPSG:2154"
        )
        # Index contigu 0..N-1 : garantit que le fid GPKG attribué par GDAL
        # (1..N dans l'ordre d'écriture) vaut exactement index + 1. Les cibles
        # et l'export MLL nomment les dolines "doline_{fid}" sur cette base.
        scored_dolines = scored_dolines.reset_index(drop=True)

        include_mnt_hillshade = self.parameterAsBool(
            parameters, self.INCLUDE_MNT_HILLSHADE, context)

        # ── Courbes de niveau (optionnel) ─────────────────────────────────
        contours = None
        contour_interval = self.parameterAsDouble(
            parameters, self.CONTOUR_INTERVAL, context)
        if contour_interval and contour_interval > 0 and mnt_path.exists():
            try:
                from karstpro.core.lidar import generate_contours
                contours = generate_contours(mnt_path, interval=contour_interval)
                feedback.pushInfo(
                    f"Courbes de niveau : {len(contours)} segments "
                    f"(équidistance {contour_interval:g} m, maîtresses tous les 10 m)"
                )
            except Exception as e:
                feedback.pushWarning(f"Courbes de niveau non générées : {e}")

        # Emprise des cibles P1 (dolines rouges) pour le zoom initial du projet.
        # Calculée ici car le .qgs est écrit avant le remplissage des couches P1.
        zoom_extent = None
        try:
            if "priorite" in scored_dolines.columns:
                _p1 = scored_dolines[scored_dolines["priorite"] == "rouge"]
                if not _p1.empty:
                    zoom_extent = tuple(_p1.total_bounds)  # (minx,miny,maxx,maxy) L93
        except Exception:
            zoom_extent = None

        # Pass topo passages GeoDataFrame if available (included as layer in gpkg)
        topo_gdf = topo.passages if topo is not None and not topo.passages.empty else None
        # Couches inventaire externes référencées (NON copiées), lecture seule.
        external_layers = []
        if cavites_connues_layer_name is not None:
            external_layers.append({
                "gpkg": str(cavites_connues_gpkg),
                "layer": cavites_connues_layer_name,
                "name": "Inventaire Cavités"})
        if tracages_layer_name is not None:
            external_layers.append({
                "gpkg": str(tracages_gpkg),
                "layer": tracages_layer_name,
                "name": "Inventaire Traçages"})
        result = package_qfield_project(
            name, scored_dolines, cav_empty,
            output_dir, reseau=reseau, geology=geology, topo=topo_gdf,
            cavites_georisques=cavites_georisques,
            contours=contours,
            external_layers=external_layers,
            zoom_extent=zoom_extent,
            include_mnt_hillshade=include_mnt_hillshade,
        )

        # Remplir les couches P1/P2/P3 immédiatement depuis les dolines scorées
        try:
            n_p1, n_p2, n_p3 = write_cibles_from_scored_dolines(
                result["gpkg"], name, scored_dolines
            )
            feedback.pushInfo(
                f"Cibles terrain : {n_p1} rouges (P1) + {n_p2} oranges (P2) + {n_p3} jaunes (P3)"
            )
        except Exception as exc:
            feedback.pushWarning(f"Écriture cibles P1/P2/P3 échouée : {exc}")

        self._log(feedback, f"Projet QField prêt : {result['gpkg']}", log_file)
        self._log(feedback, f"Log complet : {log_file}", log_file)
        _elapsed = (datetime.now() - _t0).total_seconds()
        self._log(feedback,
                  f"Exécution terminée en {_elapsed:.0f} s "
                  f"({int(_elapsed // 60)} min {int(_elapsed % 60)} s)", log_file)
        feedback.setProgress(100)
        return {self.OUTPUT_DIR: str(output_dir)}


def _merge_cavites_sources(
    cavites_utilisateur: "gpd.GeoDataFrame | None",
    cavites_georisques: "gpd.GeoDataFrame | None",
) -> "gpd.GeoDataFrame":
    """Fusionne les cavités utilisateur et Géorisques en un GDF normalisé.

    Normalise les colonnes Géorisques (nom_cavite→name, type_cavite→type,
    identifiant→reference) pour correspondre au schéma attendu par
    compute_cavites_connues_proximity().

    Returns un GeoDataFrame vide si les deux sources sont absentes/vides.
    """
    import geopandas as gpd
    import pandas as pd

    TARGET_CRS = "EPSG:2154"
    parts = []

    if cavites_utilisateur is not None and not cavites_utilisateur.empty:
        cav = cavites_utilisateur.copy()
        if cav.crs is None:
            cav = cav.set_crs(TARGET_CRS)
        elif str(cav.crs).upper() != TARGET_CRS:
            cav = cav.to_crs(TARGET_CRS)
        # Tag de source : l'inventaire utilisateur est prioritaire sur Géorisques
        # pour l'étiquetage de proximité (noms/réfs fiables vs « anonyme »).
        cav["_source"] = "inventaire"
        parts.append(cav)

    if cavites_georisques is not None and not cavites_georisques.empty:
        geo = cavites_georisques.rename(columns={
            "nom_cavite": "name",
            "type_cavite": "type",
            "identifiant": "reference",
        }).copy()
        if geo.crs is None:
            geo = geo.set_crs(TARGET_CRS)
        elif str(geo.crs).upper() != TARGET_CRS:
            geo = geo.to_crs(TARGET_CRS)
        # Conserver uniquement les colonnes compatibles + geometry
        for col in ["name", "type", "reference", "geometry"]:
            if col not in geo.columns:
                geo[col] = ""
        geo = geo[["name", "type", "reference", "geometry"]].copy()
        geo["_source"] = "georisques"
        parts.append(geo)

    if not parts:
        return gpd.GeoDataFrame(
            columns=["name", "type", "reference", "geometry"], crs=TARGET_CRS
        )

    merged = gpd.GeoDataFrame(
        pd.concat(parts, ignore_index=True), crs=TARGET_CRS
    )
    return merged
