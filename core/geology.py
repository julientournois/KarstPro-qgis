# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
# Usage commercial interdit sans autorisation écrite — julien.tournois@gmail.com
# https://polyformproject.org/licenses/noncommercial/1.0.0
import io
from pathlib import Path
import requests
import geopandas as gpd

# BRGM WFS — geoservices.brgm.fr/geologie
# Layer ms:LITHO_1M_SIMPLIFIEE : simplified 1:1 000 000 lithology polygons.
# The WFS returns GML 3.2 (not JSON) in EPSG:4326; we reproject to EPSG:2154.
# ms:GEOLOGIE does not exist on this endpoint — LITHO_1M_SIMPLIFIEE is the
# correct polygon layer for karst scoring (limestone/dolomite detection).
_BRGM_WFS_URL = "https://geoservices.brgm.fr/geologie"
_LAYER = "ms:LITHO_1M_SIMPLIFIEE"
_TARGET_CRS = "EPSG:2154"


def fetch_brgm_geology(bbox_l93: tuple) -> gpd.GeoDataFrame:
    """Downloads BRGM simplified lithology layer for the given Lambert-93 bbox.

    Queries the BRGM WFS (GML 3.2 output, reprojected to EPSG:2154).
    Returns an empty GeoDataFrame on failure rather than crashing the pipeline.

    Args:
        bbox_l93: Tuple (xmin, ymin, xmax, ymax) in Lambert-93 (metres)

    Returns:
        GeoDataFrame with lithology polygons in EPSG:2154, or empty GDF on error
    """
    xmin, ymin, xmax, ymax = bbox_l93
    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": _LAYER,
        "BBOX": f"{xmin},{ymin},{xmax},{ymax},EPSG:2154",
        "SRSNAME": "EPSG:2154",
    }
    try:
        resp = requests.get(_BRGM_WFS_URL, params=params, timeout=60)
    except requests.exceptions.RequestException as exc:
        return _empty_gdf(f"BRGM WFS connexion impossible : {exc}")

    if resp.status_code != 200:
        return _empty_gdf(
            f"BRGM WFS HTTP {resp.status_code} : {resp.text[:200]}"
        )

    # The service returns GML 3.2 — geopandas reads it via fiona/GDAL
    try:
        gdf = gpd.read_file(io.BytesIO(resp.content))
    except Exception as exc:
        return _empty_gdf(f"BRGM WFS : impossible de lire le GML — {exc}")

    if gdf.empty:
        return _empty_gdf("BRGM WFS : aucune entité dans la bbox")

    # Reproject to Lambert-93 if needed
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    if gdf.crs.to_epsg() != 2154:
        gdf = gdf.to_crs(_TARGET_CRS)

    return gdf


# dep_envelopes.gpkg est embarqué dans le plugin (karstpro/data/) — toujours dispo.
_DEP_ENVELOPES = Path(__file__).resolve().parent.parent / "data" / "dep_envelopes.gpkg"

# Cache BD Charm-50 : cherché dans plusieurs emplacements dans l'ordre.
# Si un cache existe déjà, on le réutilise (repo en dev, ou home). Sinon, le
# défaut d'ÉCRITURE est le dossier du plugin lui-même (karstpro/data/geo50k),
# pour que les cartes téléchargées restent rangées DANS le plugin.
_PLUGIN_GEO50K = Path(__file__).resolve().parent.parent / "data" / "geo50k"  # karstpro/data/geo50k


def _find_geo50k_root() -> Path:
    existing = [
        Path(__file__).resolve().parent.parent.parent / "data" / "geo50k",  # repo (dev)
        _PLUGIN_GEO50K,                                                      # plugin
        Path.home() / "karstpro_data" / "geo50k",                           # home
    ]
    for p in existing:
        if p.exists():
            return p
    # Aucun cache existant : télécharger DANS le plugin (karstpro/data/geo50k).
    return _PLUGIN_GEO50K

_GEO50K_ROOT  = _find_geo50k_root()
_BRGM_ZIP_URL = "https://infoterre.brgm.fr/telechargements/BDCharm50/GEO050K_HARM_{code}.zip"

# Mapping code département → (région, nom_dep)
# Noms en ASCII sans accents pour compatibilité chemins Windows/Linux.
# Source : découpage administratif INSEE + URL Infoterre BDCharm-50.
_DEP_REGISTRY = {
    # Auvergne-Rhône-Alpes
    "001": ("Auvergne_Rhone_Alpes",      "Ain"),
    "003": ("Auvergne_Rhone_Alpes",      "Allier"),
    "007": ("Auvergne_Rhone_Alpes",      "Ardeche"),
    "015": ("Auvergne_Rhone_Alpes",      "Cantal"),
    "026": ("Auvergne_Rhone_Alpes",      "Drome"),
    "038": ("Auvergne_Rhone_Alpes",      "Isere"),
    "042": ("Auvergne_Rhone_Alpes",      "Loire"),
    "043": ("Auvergne_Rhone_Alpes",      "Haute-Loire"),
    "063": ("Auvergne_Rhone_Alpes",      "Puy-de-Dome"),
    "069": ("Auvergne_Rhone_Alpes",      "Rhone"),
    "073": ("Auvergne_Rhone_Alpes",      "Savoie"),
    "074": ("Auvergne_Rhone_Alpes",      "Haute-Savoie"),
    # Bourgogne-Franche-Comté
    "021": ("Bourgogne_Franche_Comte",   "Cote-dOr"),
    "025": ("Bourgogne_Franche_Comte",   "Doubs"),
    "039": ("Bourgogne_Franche_Comte",   "Jura"),
    "058": ("Bourgogne_Franche_Comte",   "Nievre"),
    "070": ("Bourgogne_Franche_Comte",   "Haute-Saone"),
    "071": ("Bourgogne_Franche_Comte",   "Saone-et-Loire"),
    "089": ("Bourgogne_Franche_Comte",   "Yonne"),
    "090": ("Bourgogne_Franche_Comte",   "Territoire-de-Belfort"),
    # Bretagne
    "022": ("Bretagne",                  "Cotes-dArmor"),
    "029": ("Bretagne",                  "Finistere"),
    "035": ("Bretagne",                  "Ille-et-Vilaine"),
    "056": ("Bretagne",                  "Morbihan"),
    # Centre-Val de Loire
    "018": ("Centre_Val_de_Loire",       "Cher"),
    "028": ("Centre_Val_de_Loire",       "Eure-et-Loir"),
    "036": ("Centre_Val_de_Loire",       "Indre"),
    "037": ("Centre_Val_de_Loire",       "Indre-et-Loire"),
    "041": ("Centre_Val_de_Loire",       "Loir-et-Cher"),
    "045": ("Centre_Val_de_Loire",       "Loiret"),
    # Corse
    "02A": ("Corse",                     "Corse-du-Sud"),
    "02B": ("Corse",                     "Haute-Corse"),
    # Grand Est
    "008": ("Grand_Est",                 "Ardennes"),
    "010": ("Grand_Est",                 "Aube"),
    "051": ("Grand_Est",                 "Marne"),
    "052": ("Grand_Est",                 "Haute-Marne"),
    "054": ("Grand_Est",                 "Meurthe-et-Moselle"),
    "055": ("Grand_Est",                 "Meuse"),
    "057": ("Grand_Est",                 "Moselle"),
    "067": ("Grand_Est",                 "Bas-Rhin"),
    "068": ("Grand_Est",                 "Haut-Rhin"),
    "088": ("Grand_Est",                 "Vosges"),
    # Hauts-de-France
    "002": ("Hauts_de_France",           "Aisne"),
    "059": ("Hauts_de_France",           "Nord"),
    "060": ("Hauts_de_France",           "Oise"),
    "062": ("Hauts_de_France",           "Pas-de-Calais"),
    "080": ("Hauts_de_France",           "Somme"),
    # Île-de-France
    "075": ("Ile_de_France",             "Paris"),
    "077": ("Ile_de_France",             "Seine-et-Marne"),
    "078": ("Ile_de_France",             "Yvelines"),
    "091": ("Ile_de_France",             "Essonne"),
    "092": ("Ile_de_France",             "Hauts-de-Seine"),
    "093": ("Ile_de_France",             "Seine-Saint-Denis"),
    "094": ("Ile_de_France",             "Val-de-Marne"),
    "095": ("Ile_de_France",             "Val-dOise"),
    # Normandie
    "014": ("Normandie",                 "Calvados"),
    "027": ("Normandie",                 "Eure"),
    "050": ("Normandie",                 "Manche"),
    "061": ("Normandie",                 "Orne"),
    "076": ("Normandie",                 "Seine-Maritime"),
    # Nouvelle-Aquitaine
    "016": ("Nouvelle_Aquitaine",        "Charente"),
    "017": ("Nouvelle_Aquitaine",        "Charente-Maritime"),
    "019": ("Nouvelle_Aquitaine",        "Correze"),
    "023": ("Nouvelle_Aquitaine",        "Creuse"),
    "024": ("Nouvelle_Aquitaine",        "Dordogne"),
    "033": ("Nouvelle_Aquitaine",        "Gironde"),
    "040": ("Nouvelle_Aquitaine",        "Landes"),
    "047": ("Nouvelle_Aquitaine",        "Lot-et-Garonne"),
    "064": ("Nouvelle_Aquitaine",        "Pyrenees-Atlantiques"),
    "079": ("Nouvelle_Aquitaine",        "Deux-Sevres"),
    "086": ("Nouvelle_Aquitaine",        "Vienne"),
    "087": ("Nouvelle_Aquitaine",        "Haute-Vienne"),
    # Occitanie
    "009": ("Occitanie",                 "Ariege"),
    "011": ("Occitanie",                 "Aude"),
    "012": ("Occitanie",                 "Aveyron"),
    "030": ("Occitanie",                 "Gard"),
    "031": ("Occitanie",                 "Haute-Garonne"),
    "032": ("Occitanie",                 "Gers"),
    "034": ("Occitanie",                 "Herault"),
    "046": ("Occitanie",                 "Lot"),
    "048": ("Occitanie",                 "Lozere"),
    "065": ("Occitanie",                 "Hautes-Pyrenees"),
    "066": ("Occitanie",                 "Pyrenees-Orientales"),
    "081": ("Occitanie",                 "Tarn"),
    "082": ("Occitanie",                 "Tarn-et-Garonne"),
    # Pays de la Loire
    "044": ("Pays_de_la_Loire",          "Loire-Atlantique"),
    "049": ("Pays_de_la_Loire",          "Maine-et-Loire"),
    "053": ("Pays_de_la_Loire",          "Mayenne"),
    "072": ("Pays_de_la_Loire",          "Sarthe"),
    "085": ("Pays_de_la_Loire",          "Vendee"),
    # Provence-Alpes-Côte d'Azur
    "004": ("Provence_Alpes_Cote_Azur",  "Alpes-de-Haute-Provence"),
    "005": ("Provence_Alpes_Cote_Azur",  "Hautes-Alpes"),
    "006": ("Provence_Alpes_Cote_Azur",  "Alpes-Maritimes"),
    "013": ("Provence_Alpes_Cote_Azur",  "Bouches-du-Rhone"),
    "083": ("Provence_Alpes_Cote_Azur",  "Var"),
    "084": ("Provence_Alpes_Cote_Azur",  "Vaucluse"),
}


def _dep_gpkg_path(code: str) -> Path:
    """Retourne le chemin attendu du GPKG département dans le cache local."""
    region, dep_name = _DEP_REGISTRY[code]
    return (
        _GEO50K_ROOT / region
        / f"GEO050K_HARM_{code}_{dep_name}"
        / f"GEO050K_HARM_{code}_{dep_name}.gpkg"
    )


def _download_dep(code: str, feedback=None) -> Path | None:
    """Télécharge, extrait et construit le GPKG département si absent du cache.

    Args:
        code    : code département 3 chiffres (ex. '051')
        feedback: QgsProcessingFeedback optionnel pour les logs QGIS

    Returns:
        Path vers le GPKG département, ou None en cas d'échec.
    """
    import zipfile

    def log(msg):
        if feedback:
            feedback.pushInfo(msg)
        else:
            print(msg)

    region, dep_name = _DEP_REGISTRY[code]
    gpkg_path = _dep_gpkg_path(code)
    if gpkg_path.exists():
        return gpkg_path

    dep_dir = gpkg_path.parent
    dep_dir.mkdir(parents=True, exist_ok=True)

    url = _BRGM_ZIP_URL.format(code=code)
    log(f"  Telechargement BD Charm-50 departement {dep_name} ({code})...")

    try:
        resp = requests.get(url, timeout=120, stream=True)
        if resp.status_code != 200:
            log(f"  ERREUR HTTP {resp.status_code} pour {url}")
            return None

        zip_path = dep_dir / f"GEO050K_HARM_{code}.zip"
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                f.write(chunk)

        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(dep_dir)
        zip_path.unlink(missing_ok=True)
        log(f"  Extraction OK : {dep_dir.name}")

    except Exception as exc:
        log(f"  ERREUR telechargement {dep_name} : {exc}")
        # Supprimer le ZIP partiel pour éviter un état corrompu au prochain appel
        zip_path = dep_dir / f"GEO050K_HARM_{code}.zip"
        zip_path.unlink(missing_ok=True)
        return None

    # Construire le GPKG département
    shp = dep_dir / f"GEO050K_HARM_{code}_S_FGEOL_2154.shp"
    if not shp.exists():
        log(f"  SHP introuvable apres extraction : {shp.name}")
        return None

    try:
        gdf = gpd.read_file(shp).to_crs("EPSG:2154")
        gdf["DEP"] = code
        gdf["DEP_NOM"] = dep_name
        gdf["REGION"] = region
        gdf.to_file(str(gpkg_path), layer="formations_geologiques", driver="GPKG")
        sz = gpkg_path.stat().st_size / 1024 / 1024
        log(f"  GPKG cree : {gpkg_path.name} ({len(gdf)} formations, {sz:.1f} MB)")
    except Exception as exc:
        log(f"  ERREUR construction GPKG {dep_name} : {exc}")
        return None

    return gpkg_path


def fetch_geology_auto(bbox_l93: tuple, feedback=None) -> gpd.GeoDataFrame:
    """Charge la géologie BD Charm-50 1/50 000 automatiquement pour la bbox.

    Algorithme :
    1. Lit dep_envelopes.gpkg (112 KB) pour trouver les départements intersectant la bbox.
    2. Pour chaque département : vérifie le cache local, télécharge si absent.
    3. Charge et filtre les formations karstiques (calcaire/dolomie) dans la bbox.
    4. Fallback sur WFS BRGM 1/1 000 000 si aucun département connu ou échec.

    Args:
        bbox_l93 : (xmin, ymin, xmax, ymax) en EPSG:2154
        feedback : QgsProcessingFeedback optionnel

    Returns:
        GeoDataFrame formations karstiques en EPSG:2154.
    """
    from shapely.geometry import box

    def log(msg):
        if feedback:
            feedback.pushInfo(msg)

    # 1. Trouver les départements concernés via les enveloppes
    if not _DEP_ENVELOPES.exists():
        log("dep_envelopes.gpkg absent — fallback WFS BRGM.")
        return fetch_brgm_geology(bbox_l93)

    try:
        envelopes = gpd.read_file(str(_DEP_ENVELOPES), layer="departements")
        bbox_geom = box(*bbox_l93)
        hits = envelopes[envelopes.intersects(bbox_geom)]
    except Exception as exc:
        log(f"Enveloppes : erreur lecture ({exc}) — fallback WFS BRGM.")
        return fetch_brgm_geology(bbox_l93)

    if hits.empty:
        log("Bbox hors des departements en cache — fallback WFS BRGM.")
        return fetch_brgm_geology(bbox_l93)

    codes = list(hits["DEP"].values)
    log(
        f"Geologie BD Charm-50 1/50 000 — "
        f"{len(codes)} departement(s) : {', '.join(hits['DEP_NOM'].values)}"
    )

    # 2. Télécharger les départements manquants + charger
    gdfs = []
    for code in codes:
        if code not in _DEP_REGISTRY:
            log(f"  Departement {code} non repertorie — ignore.")
            continue

        gpkg: Path | None = _dep_gpkg_path(code)
        if gpkg is None or not gpkg.exists():
            gpkg = _download_dep(code, feedback=feedback)
        if gpkg is None:
            continue

        try:
            gdf = gpd.read_file(str(gpkg), layer="formations_geologiques",
                                bbox=bbox_l93)
            if not gdf.empty:
                gdfs.append(gdf)
        except Exception as exc:
            log(f"  Erreur lecture {code} : {exc}")

    if not gdfs:
        log("Aucune formation chargee depuis le cache — fallback WFS BRGM.")
        return fetch_brgm_geology(bbox_l93)

    import pandas as pd
    merged = gpd.GeoDataFrame(
        pd.concat(gdfs, ignore_index=True), crs="EPSG:2154"
    )

    # 3. Filtre karstique
    # Note : case=False avec ArrowStringArray nécessite RE2 (absent dans QGIS 4.0.2).
    # On normalise la colonne en minuscule et on compare avec case=True.
    if "DESCR" in merged.columns:
        descr_low = merged["DESCR"].str.lower()
        mask = (
            descr_low.str.contains("calcaire", case=True, na=False, regex=False)
            | descr_low.str.contains("dolomie",  case=True, na=False, regex=False)
            | descr_low.str.contains("dolomit",  case=True, na=False, regex=False)
        )
        karst = merged[mask].copy()
        if karst.empty:
            log("Aucune formation calcaire dans la bbox — fallback WFS BRGM.")
            return fetch_brgm_geology(bbox_l93)
        log(f"  {len(karst)} formation(s) calcaires dans la bbox.")
        return karst

    return merged


def load_local_geology(geo_path: str, bbox_l93: tuple) -> gpd.GeoDataFrame:
    """Charge la géologie locale BD Charm-50 (1/50 000) depuis un GPKG ou shapefile.

    Filtre spatialement sur la bbox et ne conserve que les formations karstiques
    (polygones dont la description contient "calcaire" — insensible à la casse).
    Normalise les colonnes vers DESCR / NOTATION pour compatibilité avec le scoring.

    Args:
        geo_path : chemin vers le GPKG Grand Est ou un shapefile département
        bbox_l93 : (xmin, ymin, xmax, ymax) en EPSG:2154

    Returns:
        GeoDataFrame formations karstiques en EPSG:2154, ou GDF vide en cas d'erreur.
    """
    from pathlib import Path

    path = Path(geo_path)
    if not path.exists():
        return _empty_gdf(f"Géologie locale introuvable : {geo_path}")

    try:
        # Lire avec filtre bbox (bbox= dans geopandas déclenche un filtre spatial GDAL)
        xmin, ymin, xmax, ymax = bbox_l93
        gdf = gpd.read_file(str(path), bbox=(xmin, ymin, xmax, ymax))
    except Exception as exc:
        return _empty_gdf(f"Géologie locale : impossible de lire {path.name} — {exc}")

    if gdf.empty:
        return _empty_gdf(f"Géologie locale : aucune formation dans la bbox ({path.name})")

    # Reprojection EPSG:2154 si nécessaire
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:2154")
    elif gdf.crs.to_epsg() != 2154:
        gdf = gdf.to_crs("EPSG:2154")

    # Normalisation des colonnes : BD Charm-50 → DESCR / NOTATION
    col_map = {}
    cols_upper = {c.upper(): c for c in gdf.columns}
    for target, candidates in [
        ("DESCR",    ["DESCR", "DESCRIPTION", "LIBELLE", "NOM"]),
        ("NOTATION", ["NOTATION", "CODE", "CODE_LEG", "CODE_GEOL"]),
    ]:
        for cand in candidates:
            if cand in cols_upper:
                col_map[cols_upper[cand]] = target
                break
    if col_map:
        gdf = gdf.rename(columns=col_map)

    # Filtre formations karstiques : DESCR contient "calcaire" (dolomie incluse)
    # Note : case=False avec ArrowStringArray nécessite RE2 (absent dans QGIS 4.0.2).
    # On normalise en minuscule et on compare avec case=True.
    if "DESCR" in gdf.columns:
        descr_low = gdf["DESCR"].str.lower()
        mask = (
            descr_low.str.contains("calcaire", case=True, na=False, regex=False) |
            descr_low.str.contains("dolomie",  case=True, na=False, regex=False) |
            descr_low.str.contains("dolomit",  case=True, na=False, regex=False)
        )
        karst = gdf[mask].copy()
        if karst.empty:
            # Pas de formation karstique dans la bbox → retourner vide
            return _empty_gdf(
                f"Géologie locale : aucune formation calcaire dans la bbox "
                f"({mask.sum()} / {len(gdf)} formations testées)"
            )
        return karst
    else:
        # Pas de colonne DESCR → retourner tout (scoring utilisera le bord externe)
        return gdf


def fetch_georisques_cavites(bbox_l93: tuple) -> gpd.GeoDataFrame:
    """Télécharge les cavités souterraines Géorisques (BRGM) pour la bbox.

    Source : WFS Géorisques, layer CAVITE_LOCALISEE
      https://www.georisques.gouv.fr/services
    Requête en EPSG:2154 directement pour éviter le problème d'ordre d'axes
    lat/lon de WFS 1.1.0 + EPSG:4326 (qui inverse X et Y lors de la lecture GML).

    Champs retournés :
      nom_cavite, type_cavite, identifiant, date_validite, reperage_geographique

    La base Géorisques est lacunaire dans certaines régions (ex. karst sous
    couverture en Champagne-Ardenne). Un résultat vide est normal et non bloquant.

    Args:
        bbox_l93: Tuple (xmin, ymin, xmax, ymax) en Lambert-93 (EPSG:2154)

    Returns:
        GeoDataFrame des cavités en EPSG:2154, ou GeoDataFrame vide en cas d'erreur.
    """
    xmin, ymin, xmax, ymax = bbox_l93

    params = {
        "SERVICE": "WFS",
        "VERSION": "1.1.0",
        "REQUEST": "GetFeature",
        "TYPENAME": "CAVITE_LOCALISEE",
        # Requête directement en L93 : pas de conversion WGS84, pas de problème
        # d'inversion lat/lon propre au GML WFS 1.1.0 + EPSG:4326.
        "BBOX": f"{xmin},{ymin},{xmax},{ymax},EPSG:2154",
        "SRSNAME": "EPSG:2154",
    }
    try:
        resp = requests.get(
            "https://www.georisques.gouv.fr/services",
            params=params,
            timeout=30,
        )
    except requests.exceptions.RequestException as exc:
        return _empty_cavites_gdf(f"Géorisques WFS connexion impossible : {exc}")

    if resp.status_code != 200:
        return _empty_cavites_gdf(
            f"Géorisques WFS HTTP {resp.status_code} : {resp.text[:200]}"
        )

    try:
        gdf = gpd.read_file(io.BytesIO(resp.content))
    except Exception as exc:
        return _empty_cavites_gdf(f"Géorisques WFS : impossible de lire le GML — {exc}")

    if gdf.empty:
        return _empty_cavites_gdf()  # normal dans les zones peu inventoriées

    # Sélectionner uniquement les colonnes utiles (présentes ou non)
    cols_wanted = ["nom_cavite", "type_cavite", "identifiant",
                   "date_validite", "reperage_geographique", "geometry"]
    cols_present = [c for c in cols_wanted if c in gdf.columns]
    gdf = gdf[cols_present].copy()

    # S'assurer que le CRS est bien L93 (le serveur renvoie EPSG:2154 si SRSNAME=EPSG:2154,
    # mais on normalise au cas où fiona/GDAL déclarerait un CRS null)
    if gdf.crs is None:
        gdf = gdf.set_crs(_TARGET_CRS)
    elif str(gdf.crs).upper() != _TARGET_CRS:
        gdf = gdf.to_crs(_TARGET_CRS)

    return gdf


def _empty_cavites_gdf(warning: str = "") -> gpd.GeoDataFrame:
    """GeoDataFrame vide aux colonnes de cavites_georisques."""
    import warnings
    if warning:
        warnings.warn(f"KarstPro/geology: {warning}", stacklevel=2)
    return gpd.GeoDataFrame(
        columns=["nom_cavite", "type_cavite", "identifiant",
                 "date_validite", "reperage_geographique", "geometry"],
        crs=_TARGET_CRS,
    )


def check_bdlisa_karst(bbox_l93: tuple) -> bool:
    """Vérifie si la bbox intersecte une entité karstique BDLISA (SURCOUCHE_KARST).

    Requête WFS légère (maxFeatures=1) — sert uniquement de guard clause dans
    karst_prep_algorithm pour avertir l'utilisateur si la zone n'est pas karstique.

    Args:
        bbox_l93: Tuple (xmin, ymin, xmax, ymax) en Lambert-93 (EPSG:2154)

    Returns:
        True  → au moins une entité karstique intersecte la bbox.
        False → aucune entité karstique détectée (zone probablement non karstique).
        True  → en cas d'erreur réseau/serveur (fail-open : on ne bloque pas le pipeline).
    """
    try:
        from pyproj import Transformer
        t = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)
        xmin, ymin, xmax, ymax = bbox_l93
        lon_min, lat_min = t.transform(xmin, ymin)
        lon_max, lat_max = t.transform(xmax, ymax)

        # WFS 1.1.0 — BBOX en ordre lat,lon pour ce serveur
        params = {
            "SERVICE": "WFS",
            "VERSION": "1.1.0",
            "REQUEST": "GetFeature",
            "TYPENAME": "SURCOUCHE_KARST",
            "BBOX": f"{lat_min},{lon_min},{lat_max},{lon_max}",
            "outputFormat": "application/json",
            "maxFeatures": "1",
        }
        resp = requests.get(
            "http://www.reseau.eaufrance.fr/geotraitements/bdlisa/services/carto/",
            params=params,
            timeout=10,
        )
        if resp.status_code != 200:
            return True  # fail-open
        return len(resp.json().get("features", [])) > 0
    except Exception:
        return True  # fail-open : erreur réseau → on ne bloque pas


def _empty_gdf(warning: str = "") -> gpd.GeoDataFrame:
    """Returns an empty GeoDataFrame, optionally printing a warning."""
    import warnings
    if warning:
        warnings.warn(f"KarstPro/geology: {warning}", stacklevel=2)
    return gpd.GeoDataFrame(columns=["geometry", "LIBELLE"], crs=_TARGET_CRS)
