# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
# Usage commercial interdit sans autorisation écrite — julien.tournois@gmail.com
# https://polyformproject.org/licenses/noncommercial/1.0.0
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterDefinition,
    QgsProcessing,
)
from pathlib import Path
import re

# NOTE: All heavy imports deferred to processAlgorithm() — see karst_prep_algorithm.py


class KarstUpdateCiblesAlgorithm(QgsProcessingAlgorithm):
    """Retire des couches cibles P1/P2/P3 toutes les dolines dont une cavité
    saisie sur le terrain (couche ``cavites`` du GeoPackage) tombe à l'intérieur
    du polygone de doline (couche ``dolines``) élargi d'un buffer GPS.

    Logique :
      1. Lire ``cavites`` (saisies terrain) et ``dolines`` (polygones).
      2. Pour chaque cavité saisie, buffer GPS → intersection avec les polygones
         de dolines → liste des dolines visitées.
      3. Pour chaque couche cibles P1/P2/P3 : supprimer les cibles dont le
         centroïde correspond à une doline visitée (tolérance 1 m).
      4. Réécrire les couches filtrées dans le GPKG.

    À lancer au retour d'une sortie terrain, après synchronisation QField.
    """

    GPKG_FILE    = "GPKG_FILE"
    SOURCE_LAYER = "SOURCE_LAYER"
    SECTEUR_NAME = "SECTEUR_NAME"
    GPS_BUFFER_M = "GPS_BUFFER_M"

    def name(self):
        return "karst_update_cibles"

    def displayName(self):
        return "KarstPro — Mettre à jour les cibles"

    def group(self):
        return "KarstPro"

    def groupId(self):
        return "karstpro"

    def createInstance(self):
        return KarstUpdateCiblesAlgorithm()

    def helpUrl(self):
        from karstpro.core.log_feedback import doc_url
        return doc_url()

    def icon(self):
        from karstpro.icons import karst_icon
        ic = karst_icon()
        return ic if ic is not None else super().icon()

    def shortHelpString(self):
        return (
            "<b>Mettre à jour les cibles après une sortie terrain.</b><br><br>"
            "Lit les cavités saisies dans QField (couche <i>cavites</i>) et "
            "supprime des couches cibles P1/P2/P3 toutes les dolines prospectées, "
            "en recoupant avec les <b>polygones de dolines</b> (plus robuste que "
            "la distance au centroïde).<br><br>"
            "<b>Méthode :</b> chaque point GPS saisie est élargi d'un buffer "
            "(imprécision GPS) puis intersecté avec les polygones de dolines. "
            "Toute doline touchée est considérée visitée et retirée des cibles.<br><br>"
            "<b>Paramètres :</b><br>"
            "• <b>GeoPackage du secteur</b> — fichier .gpkg synchronisé depuis QField<br>"
            "• <b>Couche des cavités à retirer</b> — à choisir dans la liste des "
            "couches du projet (ex : <i>cavites</i> saisies QField, "
            "<i>cavites_connues</i> répertoriées). Vide = couche <i>cavites</i> "
            "du GeoPackage par défaut<br>"
            "• <b>Buffer GPS</b> — rayon en mètres autour de chaque point saisie "
            "pour compenser l'imprécision GPS (défaut : 15 m)<br>"
            "• <b>Nom du secteur</b> (avancé) — auto-détecté depuis le GPKG ; "
            "à renseigner seulement si plusieurs jeux de cibles coexistent<br><br>"
            "<b>Résultat :</b> les couches P1/P2/P3 du GPKG sont mises à jour en place. "
            "Recharger les couches dans QGIS après exécution (clic droit → Actualiser)."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile(
            self.GPKG_FILE,
            "GeoPackage du secteur (.gpkg)",
            extension="gpkg",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.SOURCE_LAYER,
            "Couche des cavités à retirer "
            "(défaut : la couche « cavites » du GeoPackage)",
            types=[QgsProcessing.TypeVectorPoint],
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.GPS_BUFFER_M,
            "Buffer GPS — imprécision GPS (mètres)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=15.0,
            minValue=1.0,
            maxValue=100.0,
        ))
        # Optionnel : le nom du secteur est auto-détecté depuis les couches du
        # GPKG. À renseigner seulement si plusieurs jeux de cibles coexistent.
        secteur_param = QgsProcessingParameterString(
            self.SECTEUR_NAME,
            "Nom du secteur (vide = auto-détecté depuis le GPKG)",
            defaultValue="",
            optional=True,
        )
        secteur_param.setFlags(
            secteur_param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(secteur_param)

    # ------------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):
        import geopandas as gpd
        import pyogrio

        gpkg_path   = Path(self.parameterAsFile(parameters, self.GPKG_FILE, context))
        secteur     = self.parameterAsString(parameters, self.SECTEUR_NAME, context).strip()
        source_vlayer = self.parameterAsVectorLayer(parameters, self.SOURCE_LAYER, context)
        gps_buffer  = self.parameterAsDouble(parameters, self.GPS_BUFFER_M, context)

        if not gpkg_path.exists():
            raise ValueError(f"GeoPackage introuvable : {gpkg_path}")

        # ── 1. Couches disponibles ────────────────────────────────────
        # pyogrio (geopandas l'utilise) — fiona n'est pas installe dans QGIS.
        available = [str(n) for n in pyogrio.list_layers(str(gpkg_path))[:, 0]]
        feedback.pushInfo(f"Couches dans le GPKG : {', '.join(available)}")

        # ── 1b. Auto-détection du secteur si non renseigné ────────────
        # Les couches cibles sont nommées "{secteur} — cibles P1/P2/P3".
        if not secteur:
            secteurs = set()
            for layer_name in available:
                m = re.match(r"^(.*) — cibles P[123]$", layer_name)
                if m:
                    secteurs.add(m.group(1))
            if len(secteurs) == 1:
                secteur = secteurs.pop()
                feedback.pushInfo(f"Secteur auto-détecté : « {secteur} »")
            elif len(secteurs) > 1:
                raise ValueError(
                    "Plusieurs jeux de cibles dans ce GPKG "
                    f"({', '.join(sorted(secteurs))}). Renseignez le « Nom du "
                    "secteur » (paramètre avancé) pour choisir lequel mettre à jour."
                )
            else:
                raise ValueError(
                    "Aucune couche « … — cibles P1/P2/P3 » trouvée dans le GPKG. "
                    "Ce fichier a-t-il bien été préparé par KarstPro ?"
                )

        # ── 2. Couche source des cavités ──────────────────────────────
        # Soit la couche choisie dans la liste déroulante (couche du projet),
        # soit, par défaut, la couche "cavites" du GeoPackage.
        if source_vlayer is not None:
            src = source_vlayer.source()           # ex: ".../X.gpkg|layername=cavites_connues"
            src_path = src.split("|")[0]
            src_lyr = None
            for part in src.split("|")[1:]:
                if part.lower().startswith("layername="):
                    src_lyr = part.split("=", 1)[1]
            label = source_vlayer.name()
            try:
                cavites = (gpd.read_file(src_path, layer=src_lyr)
                           if src_lyr else gpd.read_file(src_path))
            except Exception as e:
                raise ValueError(f"Lecture de la couche « {label} » échouée : {e}")
        else:
            if "cavites" not in available:
                raise ValueError(
                    "Aucune couche source indiquée et couche « cavites » absente "
                    "du GeoPackage. Sélectionnez une couche de cavités."
                )
            label = "cavites"
            cavites = gpd.read_file(str(gpkg_path), layer="cavites")

        if cavites.empty:
            # Aider : lister les couches de cavités peuplées du GPKG
            suggestions = []
            for l in available:
                if "cavite" in l.lower() and "georisque" not in l.lower():
                    try:
                        if not gpd.read_file(str(gpkg_path), layer=l).empty:
                            suggestions.append(l)
                    except Exception:
                        pass
            msg = f"Couche « {label} » vide — aucune cavité à retirer."
            if suggestions:
                msg += (f" Couche(s) peuplée(s) dans le GPKG : "
                        f"{', '.join(sorted(set(suggestions)))}.")
            feedback.pushWarning(msg)
            return {}

        feedback.pushInfo(f"{len(cavites)} cavité(s) dans « {label} ».")
        cavites = _ensure_2154(cavites)

        # ── 3. Polygones de dolines ───────────────────────────────────
        if "dolines" not in available:
            feedback.pushWarning(
                "Couche 'dolines' absente — fallback sur distance au centroïde "
                f"(rayon {gps_buffer:.0f} m)."
            )
            dolines = None
        else:
            dolines = gpd.read_file(str(gpkg_path), layer="dolines")
            dolines = _ensure_2154(dolines)
            feedback.pushInfo(f"{len(dolines)} dolines chargées.")

        # ── 4. Préparer les géométries des dolines visitées ──────────
        #
        # Une cible est retirée si elle correspond à une doline « visitée ».
        # On considère une cible visitée si :
        #   (a) une cavité est à ≤ buffer GPS de la cible (cas direct, robuste), OU
        #   (b) la cible tombe dans le polygone d'une doline elle-même touchée par
        #       une cavité (utile pour les grandes dolines où la cavité est loin
        #       du centroïde).
        # On évite toute comparaison de centroïdes arrondis (fragile : un écart de
        # 1 m entre le centroïde stocké et recalculé faisait rater la suppression).
        cav_geoms = [g for g in cavites.geometry if _valid_geom(g)]
        feedback.pushInfo(f"{len(cav_geoms)} cavité(s) géolocalisée(s) utilisée(s).")

        dolines_visitees = None   # union des polygones de dolines touchés par une cavité
        if dolines is not None and not dolines.empty:
            from shapely.ops import unary_union
            dol_sindex = dolines.sindex
            touched = []
            for cav_pt in cav_geoms:
                cav_buf = cav_pt.buffer(gps_buffer)
                for j in dol_sindex.intersection(cav_buf.bounds):
                    dg = dolines.geometry.iloc[j]
                    if _valid_geom(dg) and dg.intersects(cav_buf):
                        touched.append(dg)
            if touched:
                dolines_visitees = unary_union(touched)
                feedback.pushInfo(
                    f"{len(touched)} doline(s) touchée(s) par une cavité "
                    f"(buffer {gps_buffer:.0f} m)."
                )

        # ── 5. Filtrer les couches cibles ─────────────────────────────
        cibles_layers = {
            "P1": f"{secteur} — cibles P1",
            "P2": f"{secteur} — cibles P2",
            "P3": f"{secteur} — cibles P3",
        }

        total_supprimees = 0

        for rang, layer_name in cibles_layers.items():
            if layer_name not in available:
                feedback.pushInfo(f"Couche '{layer_name}' absente — ignorée.")
                continue

            cibles = gpd.read_file(str(gpkg_path), layer=layer_name)
            if cibles.empty:
                feedback.pushInfo(f"{rang} : couche vide — ignorée.")
                continue

            cibles = _ensure_2154(cibles)
            avant  = len(cibles)
            a_supprimer = []

            for idx, cible_row in cibles.iterrows():
                cible_pt = cible_row.geometry
                if not _valid_geom(cible_pt):
                    continue

                nom = cible_row.get("name", str(idx))

                # (a) cavité directement proche de la cible ?
                dmin = min((cav.distance(cible_pt) for cav in cav_geoms),
                           default=float("inf"))
                if dmin <= gps_buffer:
                    a_supprimer.append(idx)
                    feedback.pushInfo(
                        f"  {rang} — suppression : {nom} "
                        f"(cavité à {dmin:.1f} m)"
                    )
                    continue
                # (b) cible à l'intérieur d'une doline visitée ?
                if dolines_visitees is not None and dolines_visitees.contains(cible_pt):
                    a_supprimer.append(idx)
                    feedback.pushInfo(
                        f"  {rang} — suppression : {nom} (doline visitée)"
                    )

            cibles_filtrees = cibles.drop(index=a_supprimer)
            cibles_filtrees.to_file(
                str(gpkg_path), layer=layer_name, driver="GPKG",
                layer_options={"OVERWRITE": "YES"},
            )

            supprimees = avant - len(cibles_filtrees)
            total_supprimees += supprimees
            feedback.pushInfo(
                f"{rang} ({layer_name}) : {avant} → {len(cibles_filtrees)} "
                f"({supprimees} cible(s) retirée(s))"
            )

            if feedback.isCanceled():
                break

        # ── 6. Résumé ─────────────────────────────────────────────────
        feedback.pushInfo("=" * 50)
        feedback.pushInfo(
            f"Mise à jour terminée — {total_supprimees} cible(s) retirée(s) au total."
        )
        feedback.pushInfo(
            "Recharger les couches P1/P2/P3 dans QGIS pour voir les changements "
            "(clic droit → Actualiser)."
        )
        return {}


# ── Utilitaires ────────────────────────────────────────────────────────────────

def _valid_geom(geom) -> bool:
    """True si geom est une géométrie shapely exploitable.

    Les couches peuvent contenir des entités sans géométrie : geopandas les
    renvoie tantôt en None, tantôt en float NaN selon le driver. On filtre les
    deux (et tout objet dépourvu de .buffer).
    """
    if geom is None:
        return False
    if not hasattr(geom, "buffer"):   # exclut float/NaN et autres non-géométries
        return False
    try:
        return not geom.is_empty
    except Exception:
        return False


def _ensure_2154(gdf):
    if gdf.crs is None:
        return gdf.set_crs("EPSG:2154")
    if gdf.crs.to_epsg() != 2154:
        return gdf.to_crs("EPSG:2154")
    return gdf
