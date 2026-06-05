# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
# Usage commercial interdit sans autorisation écrite — julien.tournois@gmail.com
# https://polyformproject.org/licenses/noncommercial/1.0.0
from pathlib import Path
from typing import Optional
import geopandas as gpd
import sqlite3


def package_qfield_project(secteur_name: str,
                            dolines: gpd.GeoDataFrame,
                            cavites: gpd.GeoDataFrame,
                            output_dir: Path,
                            reseau: Optional[gpd.GeoDataFrame] = None,
                            geology: Optional[gpd.GeoDataFrame] = None,
                            topo: Optional[gpd.GeoDataFrame] = None,
                            cavites_georisques: Optional[gpd.GeoDataFrame] = None,
                            contours: Optional[gpd.GeoDataFrame] = None,
                            external_layers: Optional[list] = None,
                            zoom_extent: Optional[tuple] = None,
                            include_mnt_hillshade: bool = True) -> dict:
    """``external_layers`` : couches inventaire référencées (NON copiées) dans le
    projet, en lecture seule QField. Liste de dicts ``{"gpkg", "layer", "name"}``
    (cavités connues, traçages). Permet de garder l'inventaire dans son fichier
    partagé sans le dupliquer dans le package."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    gpkg_path = output_dir / f"{secteur_name}.gpkg"

    from karstpro.core.gpkg import _make_empty_layer, CIBLES_SCHEMA

    p1_name = f"{secteur_name} — cibles P1"
    p2_name = f"{secteur_name} — cibles P2"
    p3_name = f"{secteur_name} — cibles P3"
    layers = ["dolines", "cavites", p1_name, p2_name, p3_name]
    dolines.to_file(gpkg_path, layer="dolines", driver="GPKG")
    cavites.to_file(gpkg_path, layer="cavites", driver="GPKG")
    # Couches cibles vides — peuplées immédiatement depuis les dolines scorées,
    # puis éventuellement remplacées par l'export MLL (ordre de visite optimal)
    empty_cibles = _make_empty_layer(CIBLES_SCHEMA, crs="EPSG:2154", geom_type="Point")
    empty_cibles.to_file(gpkg_path, layer=p1_name, driver="GPKG")
    empty_cibles.to_file(gpkg_path, layer=p2_name, driver="GPKG")
    empty_cibles.to_file(gpkg_path, layer=p3_name, driver="GPKG")
    if reseau is not None and not reseau.empty:
        reseau.to_file(gpkg_path, layer="hydrologie", driver="GPKG")
        layers.append("hydrologie")
    if geology is not None and not geology.empty:
        geology.to_file(gpkg_path, layer="geologie", driver="GPKG")
        layers.append("geologie")
    if topo is not None and not topo.empty:
        topo.to_file(gpkg_path, layer="topo_reseau", driver="GPKG")
        layers.append("topo_reseau")
    # cavites_connues / tracages ne sont plus copiés ici : ils sont référencés
    # depuis leur gpkg inventaire externe via external_layers (read-only QField).
    if cavites_georisques is not None and not cavites_georisques.empty:
        cavites_georisques.to_file(gpkg_path, layer="cavites_georisques", driver="GPKG")
        layers.append("cavites_georisques")
    if contours is not None and not contours.empty:
        contours.to_file(gpkg_path, layer="courbes_niveau", driver="GPKG")
        layers.append("courbes_niveau")

    # Force le type géométrie déclaré des couches éditables vides : pyogrio
    # écrit « GEOMETRY » (générique) sur une couche sans entité, ce qui empêche
    # QField de capturer la position GPS (entités sans géométrie). cf. gpkg.py.
    from karstpro.core.gpkg import _force_gpkg_geom_types
    _force_gpkg_geom_types(gpkg_path, {"cavites": "POINT"})

    # Embed QGIS layer styles in GeoPackage (layer_styles table)
    # QGIS reads these automatically when the .gpkg is opened
    _embed_styles(gpkg_path)
    _fix_gpkg_crs(gpkg_path)

    qgs_path = output_dir / f"{secteur_name}.qgs"
    try:
        _write_qgs_project(secteur_name, gpkg_path, layers, qgs_path,
                           zoom_extent=zoom_extent,
                           include_mnt_hillshade=include_mnt_hillshade,
                           external_layers=external_layers)
    except ImportError:
        # Hors contexte QGIS (tests, CLI) — on génère le QGS sans l'API QGIS.
        qgs_path.write_text(
            _generate_qgs(secteur_name, gpkg_path, layers), encoding="utf-8"
        )

    return {"gpkg": gpkg_path, "qgs": qgs_path}


def write_cibles_from_scored_dolines(
    gpkg_path: Path,
    secteur_name: str,
    scored_dolines: gpd.GeoDataFrame,
) -> tuple[int, int, int]:
    """
    Écrit les couches ``{secteur} — cibles P1`` (rouge), ``P2`` (orange)
    et ``P3`` (jaune) dans le GeoPackage à partir des dolines scorées.

    Appelé directement depuis karst_prep_algorithm après le calcul des scores,
    sans passer par l'export MLL.  L'export MLL peut ensuite remplacer
    ces couches avec un ordre de visite optimisé.

    Returns
    -------
    (n_p1, n_p2, n_p3) : nombre de cibles écrites dans chaque couche.
    """
    from shapely.geometry import Point

    p1_name = f"{secteur_name} — cibles P1"
    p2_name = f"{secteur_name} — cibles P2"
    p3_name = f"{secteur_name} — cibles P3"

    def _build_cibles_gdf(subset: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        rows = []
        for _, row in subset.iterrows():
            centroid = row.geometry.centroid if row.geometry else None
            if centroid is None:
                continue
            rows.append({
                # row.name = index 0-based ; +1 pour coller au fid GPKG (1-based)
                # de la couche dolines et a l'export MLL. ID unique partout.
                "name": f"doline_{row.name + 1}",
                "priorite": row.get("priorite", ""),
                "score": row.get("score"),
                "score_morpho": row.get("score_morpho"),
                "score_positionnel": row.get("score_positionnel"),
                "surface_m2": row.get("surface_m2"),
                "profondeur_m": row.get("profondeur_m"),
                "ratio_ps": row.get("ratio_ps"),
                "pente_max_bord": row.get("pente_max_bord"),
                "lisere": bool(row.get("lisere", False)),
                "cold_air_index": row.get("cold_air_index"),
                "type": "",
                "developpement_estime": None,
                "topographiable": 0,
                "lien_topo": "",
                "comment": "",
                "geometry": Point(centroid.x, centroid.y),
            })
        return gpd.GeoDataFrame(rows, crs="EPSG:2154") if rows else None

    if "priorite" not in scored_dolines.columns:
        return (0, 0, 0)
    rouges  = scored_dolines[scored_dolines["priorite"] == "rouge"]
    oranges = scored_dolines[scored_dolines["priorite"] == "orange"]
    jaunes  = scored_dolines[scored_dolines["priorite"] == "jaune"]

    gdf_p1 = _build_cibles_gdf(rouges)
    gdf_p2 = _build_cibles_gdf(oranges)
    gdf_p3 = _build_cibles_gdf(jaunes)

    if gdf_p1 is not None:
        gdf_p1.to_file(str(gpkg_path), layer=p1_name, driver="GPKG",
                       layer_options={"OVERWRITE": "YES"})
    if gdf_p2 is not None:
        gdf_p2.to_file(str(gpkg_path), layer=p2_name, driver="GPKG",
                       layer_options={"OVERWRITE": "YES"})
    if gdf_p3 is not None:
        gdf_p3.to_file(str(gpkg_path), layer=p3_name, driver="GPKG",
                       layer_options={"OVERWRITE": "YES"})

    _fix_gpkg_crs(gpkg_path)
    return (len(rouges), len(oranges), len(jaunes))


def _fix_gpkg_crs(gpkg_path: Path) -> None:
    """Force l'entrée EPSG:2154 correcte dans gpkg_spatial_ref_sys.

    Fiona/GDAL écrit parfois srs_id=99999 organization=NONE pour EPSG:2154,
    ce que QGIS 4 ne reconnaît pas. On insère/remplace l'entrée standard
    en utilisant pyproj comme source autoritaire du WKT.
    """
    from pyproj import CRS as ProjCRS
    crs = ProjCRS.from_epsg(2154)
    wkt2 = crs.to_wkt()
    wkt1 = crs.to_wkt(version="WKT1_GDAL")

    with sqlite3.connect(gpkg_path) as con:
        cur = con.cursor()
        # Vérifier si la colonne definition_12_063 existe (GPKG >= 1.2.1)
        cols = {row[1] for row in cur.execute("PRAGMA table_info(gpkg_spatial_ref_sys)")}
        if "definition_12_063" in cols:
            cur.execute("""
                INSERT OR REPLACE INTO gpkg_spatial_ref_sys
                    (srs_name, srs_id, organization, organization_coordsys_id,
                     definition, definition_12_063)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("RGF93 v1 / Lambert-93", 2154, "EPSG", 2154, wkt1, wkt2))
        else:
            cur.execute("""
                INSERT OR REPLACE INTO gpkg_spatial_ref_sys
                    (srs_name, srs_id, organization, organization_coordsys_id, definition)
                VALUES (?, ?, ?, ?, ?)
            """, ("RGF93 v1 / Lambert-93", 2154, "EPSG", 2154, wkt1))

        cur.execute("UPDATE gpkg_geometry_columns SET srs_id=2154 WHERE srs_id=99999")
        cur.execute("UPDATE gpkg_contents SET srs_id=2154 WHERE srs_id=99999")
        con.commit()


def _embed_styles(gpkg_path: Path) -> None:
    """Writes QGIS layer styles into the GeoPackage layer_styles table."""
    with sqlite3.connect(gpkg_path) as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS layer_styles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                f_table_catalog TEXT, f_table_schema TEXT, f_table_name TEXT,
                f_geometry_column TEXT, styleName TEXT, styleQML TEXT,
                styleSLD TEXT, useAsDefault INTEGER, description TEXT,
                owner TEXT, ui TEXT, update_time DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("DELETE FROM layer_styles WHERE f_table_name = 'dolines'")
        cur.execute(
            "INSERT INTO layer_styles "
            "(f_table_catalog, f_table_schema, f_table_name, f_geometry_column, "
            " styleName, styleQML, useAsDefault) VALUES (?,?,?,?,?,?,?)",
            ("", "", "dolines", "geometry", "priorite", _DOLINES_QML, 1),
        )
        con.commit()


# QML categorized renderer for dolines — colours by priorite field
_DOLINES_QML = """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="Symbology">
  <renderer-v2 type="categorizedSymbol" attr="priorite" forceraster="0" symbollevels="0" enableorderby="0">
    <categories>
      <category value="rouge" label="Rouge — très fort intérêt" render="true">
        <symbol type="fill" name="rouge" clip_to_extent="1" alpha="0.85" force_rhr="0">
          <data_defined_properties><Option type="Map"><Option name="name" type="QString" value=""/><Option name="properties"/><Option name="type" type="QString" value="collection"/></Option></data_defined_properties>
          <layer class="SimpleFill" enabled="1" pass="0" locked="0">
            <Option type="Map">
              <Option name="color" type="QString" value="214,47,39,217"/>
              <Option name="outline_color" type="QString" value="100,0,0,255"/>
              <Option name="outline_width" type="QString" value="0.4"/>
              <Option name="style" type="QString" value="solid"/>
            </Option>
          </layer>
        </symbol>
      </category>
      <category value="orange" label="Orange — bon intérêt" render="true">
        <symbol type="fill" name="orange" clip_to_extent="1" alpha="0.85" force_rhr="0">
          <data_defined_properties><Option type="Map"><Option name="name" type="QString" value=""/><Option name="properties"/><Option name="type" type="QString" value="collection"/></Option></data_defined_properties>
          <layer class="SimpleFill" enabled="1" pass="0" locked="0">
            <Option type="Map">
              <Option name="color" type="QString" value="255,127,0,217"/>
              <Option name="outline_color" type="QString" value="150,70,0,255"/>
              <Option name="outline_width" type="QString" value="0.4"/>
              <Option name="style" type="QString" value="solid"/>
            </Option>
          </layer>
        </symbol>
      </category>
      <category value="jaune" label="Jaune — intérêt modéré" render="true">
        <symbol type="fill" name="jaune" clip_to_extent="1" alpha="0.85" force_rhr="0">
          <data_defined_properties><Option type="Map"><Option name="name" type="QString" value=""/><Option name="properties"/><Option name="type" type="QString" value="collection"/></Option></data_defined_properties>
          <layer class="SimpleFill" enabled="1" pass="0" locked="0">
            <Option type="Map">
              <Option name="color" type="QString" value="255,215,0,217"/>
              <Option name="outline_color" type="QString" value="150,120,0,255"/>
              <Option name="outline_width" type="QString" value="0.4"/>
              <Option name="style" type="QString" value="solid"/>
            </Option>
          </layer>
        </symbol>
      </category>
      <category value="gris" label="Gris — faible intérêt" render="true">
        <symbol type="fill" name="gris" clip_to_extent="1" alpha="0.85" force_rhr="0">
          <data_defined_properties><Option type="Map"><Option name="name" type="QString" value=""/><Option name="properties"/><Option name="type" type="QString" value="collection"/></Option></data_defined_properties>
          <layer class="SimpleFill" enabled="1" pass="0" locked="0">
            <Option type="Map">
              <Option name="color" type="QString" value="150,150,150,180"/>
              <Option name="outline_color" type="QString" value="80,80,80,255"/>
              <Option name="outline_width" type="QString" value="0.3"/>
              <Option name="style" type="QString" value="solid"/>
            </Option>
          </layer>
        </symbol>
      </category>
    </categories>
    <symbols/>
  </renderer-v2>
</qgis>"""


def _write_qgs_project(name: str, gpkg_path: Path, layers: list,
                        qgs_path: Path, zoom_extent=None,
                        include_mnt_hillshade: bool = True,
                        external_layers: list = None) -> None:
    """Écrit le projet QGIS via l'API QgsProject — garantit un CRS correct.

    Couches éditables (cavites) : QFieldSync action=offline + geomSource=gps.
    Couches lecture seule : QFieldSync action=readonly.
    Couches masquées par défaut : dolines, hydrologie, geologie, cibles P3.
    """
    from qgis.core import (
        QgsProject, QgsVectorLayer, QgsCoordinateReferenceSystem,
        QgsRectangle, QgsFieldConstraints,
    )

    EDITABLE = {"cavites"}
    HIDDEN_BY_DEFAULT = {"dolines", "hydrologie", "geologie"}

    gpkg_str = str(gpkg_path)
    crs = QgsCoordinateReferenceSystem("EPSG:2154")

    proj = QgsProject()
    proj.setCrs(crs)
    proj.setTitle(f"{name} — KarstPro")
    # Chemins relatifs → le .qgs et le .gpkg restent portables sur toute machine.
    # writeEntry("Paths","/Absolute",False) est l'API stable QGIS 3.x/4.x.
    proj.writeEntry("Paths", "/Absolute", False)

    root = proj.layerTreeRoot()
    # Vider l'arbre par défaut
    root.removeAllChildren()

    extent_dolines = None  # repli si zoom_extent absent

    for layer_name in layers:
        display_name = layer_name if layer_name.startswith(name) else f"{name} — {layer_name}"
        uri = f"{gpkg_str}|layername={layer_name}"
        vl = QgsVectorLayer(uri, display_name, "ogr")
        if not vl.isValid():
            continue
        vl.setCrs(crs)

        # Propriétés QFieldSync
        if layer_name in EDITABLE:
            vl.setCustomProperty("QFieldSync/action", "offline")
            vl.setCustomProperty("QFieldSync/geomSource", "gps")
            # Contrainte dure : interdit d'enregistrer une entité sans
            # géométrie. Sans ça, QField laisse valider le formulaire même si
            # le GPS est coupé ou sans fix (couvert forestier en karst) → des
            # points fantômes (attributs OK, position NULL) qu'on ne voit qu'au
            # bureau. QField applique les contraintes de champ dures (blocage
            # du commit). On la pose sur le champ "name" (sinon le 1er champ).
            fields = vl.fields()
            idx = fields.indexOf("name")
            if idx < 0 and fields.count() > 0:
                idx = 0
            if idx >= 0:
                vl.setConstraintExpression(
                    idx, "$geometry IS NOT NULL",
                    "Position GPS obligatoire : activez la localisation "
                    "avant d'enregistrer",
                )
                vl.setFieldConstraint(
                    idx, QgsFieldConstraints.ConstraintExpression,
                    QgsFieldConstraints.ConstraintStrengthHard,
                )
        else:
            vl.setCustomProperty("QFieldSync/action", "readonly")

        if layer_name == "courbes_niveau":
            _style_contours(vl)

        # Repli pour le zoom initial si zoom_extent n'est pas fourni
        if layer_name == "dolines" and vl.featureCount() > 0:
            extent_dolines = vl.extent()

        proj.addMapLayer(vl, addToLegend=False)
        node = root.addLayer(vl)
        if layer_name in HIDDEN_BY_DEFAULT or layer_name.endswith("cibles P3"):
            node.setItemVisibilityChecked(False)

    # ── Couches inventaire externes (cavités connues, traçages) ────────────
    # Référencées depuis leur gpkg partagé (NON copiées), lecture seule QField.
    # QFieldSync en fera un snapshot dans le paquet cloud ; au bureau elles
    # pointent l'inventaire vivant.
    for ext in (external_layers or []):
        ext_path = ext.get("gpkg")
        ext_layer = ext.get("layer")
        if not ext_path or not ext_layer:
            continue
        uri = f"{ext_path}|layername={ext_layer}"
        disp = ext.get("name") or ext_layer
        vl = QgsVectorLayer(uri, disp, "ogr")
        if not vl.isValid():
            continue
        vl.setCustomProperty("QFieldSync/action", "readonly")
        proj.addMapLayer(vl, addToLegend=False)
        root.addLayer(vl)

    # ── MNT en ombrage (relief gris pour reperer dolines/depressions) ──────
    # Reference relative lidar_work/mnt.tif ; place sous les couches vecteur.
    # Toggle include_mnt_hillshade : décocher exclut le MNT du projet (et donc
    # du paquet QFieldCloud, qui ignore le flag QFieldSync/cloud_action=remove).
    if include_mnt_hillshade:
        _add_mnt_hillshade(proj, root, gpkg_path.parent, crs)

    # ── Fond de plan IGN (WMS) tout en bas, sous l'ombrage MNT ─────────────
    _add_plan_ign(proj, root, crs)

    # ── Vue initiale : zoom sur les cibles P1 (sinon emprise des dolines) ──
    # Évite d'ouvrir le projet sur une zone vide. zoom_extent = (minx,miny,maxx,maxy)
    # en L93, fourni par la préparation (les couches P1 sont vides à ce stade).
    initial = None
    if zoom_extent is not None:
        try:
            initial = QgsRectangle(*[float(v) for v in zoom_extent])
        except Exception:
            initial = None
    if (initial is None or initial.isEmpty()) and extent_dolines is not None:
        initial = extent_dolines
    if initial is not None and not initial.isEmpty():
        try:
            from qgis.core import QgsReferencedRectangle
            ext = QgsRectangle(initial)
            margin = max(ext.width(), ext.height()) * 0.15
            ext.grow(margin if margin > 0 else 250.0)
            proj.viewSettings().setDefaultViewExtent(
                QgsReferencedRectangle(ext, crs))
        except Exception:
            pass

    proj.write(str(qgs_path))

    # QgsProject.write() crée des fichiers auxiliaires parasites — on les supprime.
    for pattern in ("*_styles.db", "*_attachments.zip"):
        for f in qgs_path.parent.glob(pattern):
            f.unlink(missing_ok=True)


def _style_contours(vl) -> None:
    """Style la couche courbes_niveau : lignes fines, maîtresses (maitresse=1)
    en gras avec étiquette de cote « NNN m ». Best-effort, jamais bloquant.
    """
    # ── Rendu : règle fine (intermédiaires) + règle épaisse (maîtresses) ──
    try:
        from qgis.core import QgsLineSymbol, QgsRuleBasedRenderer
        root_rule = QgsRuleBasedRenderer.Rule(None)
        inter = QgsLineSymbol.createSimple(
            {"line_color": "166,124,82,180", "line_width": "0.12"})
        maitr = QgsLineSymbol.createSimple(
            {"line_color": "120,80,40,255", "line_width": "0.45"})
        r1 = QgsRuleBasedRenderer.Rule(inter, filterExp='"maitresse" = 0',
                                       label="intermédiaire")
        r2 = QgsRuleBasedRenderer.Rule(maitr, filterExp='"maitresse" = 1',
                                       label="maîtresse")
        root_rule.appendChild(r1)
        root_rule.appendChild(r2)
        vl.setRenderer(QgsRuleBasedRenderer(root_rule))
    except Exception:
        pass

    # ── Étiquettes de cote, uniquement sur les courbes maîtresses ─────────
    try:
        from qgis.core import (
            QgsPalLayerSettings, QgsTextFormat, QgsRuleBasedLabeling,
        )
        pal = QgsPalLayerSettings()
        pal.fieldName = "format_number(\"ELEV\", 0) || ' m'"
        pal.isExpression = True
        # Placement le long de la ligne — l'enum a bougé entre QGIS 3 et 4.
        try:
            from qgis.core import Qgis
            pal.placement = Qgis.LabelPlacement.Line
        except Exception:
            try:
                pal.placement = QgsPalLayerSettings.Line
            except Exception:
                pass
        try:
            fmt = QgsTextFormat()
            fmt.setSize(8)
            pal.setFormat(fmt)
        except Exception:
            pass

        root_lbl = QgsRuleBasedLabeling.Rule(None)
        rule = QgsRuleBasedLabeling.Rule(pal)
        rule.setFilterExpression('"maitresse" = 1')
        root_lbl.appendChild(rule)
        vl.setLabeling(QgsRuleBasedLabeling(root_lbl))
        vl.setLabelsEnabled(True)
    except Exception:
        pass
    # NB : le style des courbes n'est PAS persiste dans le .gpkg
    # (saveStyleToDatabase ouvre le GeoPackage en mode WAL et laisse des
    # fichiers .gpkg-wal/.gpkg-shm). Le rendu vit donc uniquement dans le .qgs.


def _add_plan_ign(proj, root, crs) -> None:
    """Ajoute le Plan IGN (WMS Geoplateforme) tout en bas du projet.

    Couche raster WMS (GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2). Visible par defaut
    (fond de carte) ; placee tout en bas, sous l'ombrage MNT. Necessite une
    connexion internet. Exclue du packaging QField.
    Sans effet si la couche WMS est invalide (hors-ligne au moment de la prep).
    """
    try:
        from qgis.core import QgsRasterLayer
        uri = (
            "crs=EPSG:2154&dpiMode=7&format=image/png"
            "&layers=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&styles="
            "&url=https://data.geopf.fr/wms-r/wms"
        )
        rl = QgsRasterLayer(uri, "Plan IGN", "wms")
        if not rl.isValid():
            return
        rl.setCustomProperty("QFieldSync/action", "remove")
        proj.addMapLayer(rl, addToLegend=False)
        node = root.addLayer(rl)            # ajoute en fin => tout en bas
        node.setItemVisibilityChecked(True)   # visible par defaut (fond de carte)
    except Exception:
        return


def _add_mnt_hillshade(proj, root, output_dir: Path, crs) -> None:
    """Ajoute le MNT (lidar_work/mnt.tif) en ombrage multidirectionnel au projet.

    - chemin relatif (portable),
    - rendu Hillshade multidirectionnel + reechantillonnage bilineaire au zoom,
    - opacite 70 % (laisse transparaitre le Plan IGN dessous),
    - place en bas de l'arbre (sous les vecteurs),
    - exclu du packaging QFieldSync (raster volumineux).
    Sans effet si le MNT est absent.
    """
    mnt_path = output_dir / "lidar_work" / "mnt.tif"
    if not mnt_path.exists():
        return
    try:
        from qgis.core import QgsRasterLayer, QgsHillshadeRenderer
        rl = QgsRasterLayer(str(mnt_path), "MNT (ombrage)", "gdal")
        if not rl.isValid():
            return
        rl.setCrs(crs)

        renderer = QgsHillshadeRenderer(rl.dataProvider(), 1, 315.0, 45.0)
        try:
            renderer.setMultiDirectional(True)
        except Exception:
            pass
        rl.setRenderer(renderer)

        # Reechantillonnage bilineaire au zoom avant (supprime l'effet pixelise)
        try:
            from qgis.core import QgsBilinearRasterResampler, Qgis
            rf = rl.resampleFilter()
            if rf is not None:
                rf.setZoomedInResampler(QgsBilinearRasterResampler())
            rl.setResamplingStage(Qgis.RasterResamplingStage.Provider)
        except Exception:
            pass

        # Opacite reduite : laisse transparaitre le Plan IGN (fond de carte)
        # sous l'ombrage, tout en gardant le relief lisible.
        try:
            rl.renderer().setOpacity(0.70)
        except Exception:
            pass

        # Exclut le raster du packaging QField *câble* (USB/cartouche).
        # NB : QFieldCloud ignore ce flag (cloud_converter copie tous les
        # rasters) — l'exclusion cloud passe par le toggle include_mnt_hillshade.
        rl.setCustomProperty("QFieldSync/action", "remove")

        proj.addMapLayer(rl, addToLegend=False)
        # addLayer ajoute en fin de fratrie => bas de l'arbre => sous les vecteurs
        root.addLayer(rl)
    except Exception:
        # L'ombrage est un confort : ne jamais faire echouer la preparation pour ca
        return


# Conservé pour les tests unitaires hors QGIS
def _generate_qgs(name: str, gpkg_path: Path, layers: list) -> str:
    """Génère un QGS minimal hors contexte QGIS (tests uniquement)."""
    from pyproj import CRS as ProjCRS
    wkt = ProjCRS.from_epsg(2154).to_wkt()
    srs_xml = f"""    <spatialrefsys nativeFormat="Wkt">
      <wkt>{wkt}</wkt>
      <srid>2154</srid>
      <authid>EPSG:2154</authid>
      <description>RGF93 v1 / Lambert-93</description>
      <projectionacronym>lcc</projectionacronym>
      <ellipsoidacronym>EPSG:7019</ellipsoidacronym>
      <geographicflag>false</geographicflag>
    </spatialrefsys>"""

    import re

    EDITABLE = {"cavites"}
    HIDDEN_BY_DEFAULT = {"dolines", "hydrologie", "geologie"}

    def _slug(s):
        return re.sub(r"[^a-zA-Z0-9]", "_", s)

    # Chemin relatif : le .qgs et le .gpkg sont dans le même dossier.
    gpkg_posix = Path(gpkg_path).name
    layer_parts, tree_parts = [], []

    for layer in layers:
        # ID stable (pas d'UUID) — les noms de couches sont uniques dans un projet.
        lid = _slug(layer)
        display_name = layer if layer.startswith(name) else f"{name} — {layer}"
        qfs = ("offline" if layer in EDITABLE else "readonly")
        gps = '\n        <property key="QFieldSync/geomSource" value="gps"/>' if layer in EDITABLE else ""
        checked = "Qt::Unchecked" if (layer in HIDDEN_BY_DEFAULT or layer.endswith("cibles P3")) else "Qt::Checked"

        layer_parts.append(f"""    <maplayer type="vector">
      <id>{lid}</id>
      <layername>{display_name}</layername>
      <datasource>{gpkg_posix}|layername={layer}</datasource>
      <provider>ogr</provider>
      <srs>{srs_xml}</srs>
      <customproperties>
        <property key="QFieldSync/action" value="{qfs}"/>{gps}
      </customproperties>
    </maplayer>""")
        tree_parts.append(
            f'    <layer-tree-layer checked="{checked}" id="{lid}" name="{display_name}" expanded="1"/>'
        )

    return f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34">
  <title>{name} — KarstPro</title>
  <projectCrs>{srs_xml}</projectCrs>
  <layer-tree-group name="" checked="Qt::Checked" expanded="1">
    <custom-order enabled="0"/>
{chr(10).join(tree_parts)}
  </layer-tree-group>
  <projectlayers>
{chr(10).join(layer_parts)}
  </projectlayers>
</qgis>"""


