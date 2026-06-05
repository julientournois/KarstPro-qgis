# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
# Usage commercial interdit sans autorisation écrite — julien.tournois@gmail.com
# https://polyformproject.org/licenses/noncommercial/1.0.0
import json
from pathlib import Path
import geopandas as gpd
import pandas as pd

# ── Schéma partagé chargé depuis config/karst_schema.json ───────────────────
# Source de vérité unique pour les couches échangées avec Karst Entry
# (cavites, cavites_connues, tracages). Copie locale par projet : les deux
# plugins restent indépendants mais doivent porter le même contrat.
_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "config" / "karst_schema.json"

# Repli : KarstPro doit rester fonctionnel si le JSON est absent/illisible.
# NB : le schéma de l'inventaire (cavites_connues) n'est plus matérialisé en
# Python — KarstPro le détecte/lit mais ne le crée plus. Source de vérité :
# karst_schema.json (côté Karst Entry pour la création).
_FALLBACK_CAVITES = {
    "name": "str", "type": "str", "reference": "str", "comment": "str",
    "dim_entree_longueur": "float", "dim_entree_largeur": "float",
    "developpement_estime": "float", "topographiable": "int64", "lien_topo": "str",
    "date_disc": "str", "date_expl": "str", "explorers": "str", "photos": "str",
}


def _load_layer_fields(layer_key: str, fallback: dict) -> dict:
    """Champs {nom: type} d'une couche depuis karst_schema.json, ou repli."""
    try:
        data = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
        fields = data["layers"][layer_key]["fields"]
        return dict(fields) if fields else fallback
    except (OSError, KeyError, ValueError, TypeError):
        return fallback


# Noyau cavité partagé (cavites) — produit par KarstPro, édité par Karst Entry.
CAVITES_SCHEMA = _load_layer_fields("cavites", _FALLBACK_CAVITES)

DOLINES_SCHEMA = {
    "surface_m2": "float",
    "profondeur_m": "float",
    "altitude_m": "float",      # altitude du centroïde (MNT IGN 1 m)
    "score_morpho": "float",
    "ratio_ps": "float",        # P/√S — indicateur de verticalité
    "pente_max_bord": "float",  # p90 de pente sur l'anneau périphérique 5 m (°) — v2
    "lisere": "bool",           # True = appartient à un liseré de dolines alignées
    "cold_air_index": "float",  # indice piégeage air froid [0–1] — INFORMATIF (hors score v2)
    "tpi_500m": "float",        # Topographic Position Index vs moyenne 500 m (m) — v2
    "score": "float",
    "priorite": "str",          # rouge/orange/jaune/gris
    # ── Composantes du score et informatives (pour l'analyse MLL) ────
    "circularite": "float",            # 4π·S/P² ∈ [0,1] — 1=cercle, <0.4=allongé/fossé — INFORMATIF
    "bassin_versant_m2": "float",     # surface drainée vers la doline depuis l'amont (m²)
    "type_doline": "str",             # doline / doline-perte / perte (auto depuis flow acc)
    "comp_absorption": "bool",        # True si bassin_versant_m2 ≥ seuil doline-perte (5 000 m²)
    "comp_geologie": "bool",          # centroïde sur formation karstifiable
    "comp_geologie_dist_m": "float",  # distance au bord du polygone karstifiable (m)
    "comp_dist_reseau_m": "float",    # distance au passage topo le plus proche (m) — INFORMATIF
    "comp_in_couloir": "bool",        # dans le couloir de galeries (buffer 500 m) — INFORMATIF
    "comp_bonus_decouverte": "bool",  # bonus exceptionnel (prof > 5 m hors couloir)
    "comp_densite_500m": "int64",     # nb de dolines voisines dans 500 m — INFORMATIF
}

# Couche de cibles terrain — points à prospecter (alimentée par l'export MLL)
CIBLES_SCHEMA = {
    "name": "str",              # nom provisoire de la cible (ex. doline_42)
    "priorite": "str",          # rouge / orange
    "score": "float",
    "score_morpho": "float",
    "surface_m2": "float",
    "profondeur_m": "float",
    "ratio_ps": "float",
    "pente_max_bord": "float",
    "lisere": "bool",
    "cold_air_index": "float",  # informatif
    "tpi_500m": "float",        # v2
    "type": "str",
    "developpement_estime": "float",
    "topographiable": "int64",
    "lien_topo": "str",
    "comment": "str",
}


def _make_empty_layer(schema: dict, crs: str = "EPSG:2154",
                      geom_type: str = "Polygon") -> gpd.GeoDataFrame:
    data = {col: pd.Series(dtype=dtype) for col, dtype in schema.items()}
    gdf = gpd.GeoDataFrame(data)
    gdf = gdf.set_geometry(gpd.GeoSeries([], dtype="geometry"))
    gdf = gdf.set_crs(crs)
    # Mémorise le type voulu : une GeoSeries vide est non typée, donc pyogrio
    # écrit un GPKG en type générique « GEOMETRY ». Sur les couches éditables
    # (cavites), QField ne reconnaît alors pas une couche de
    # points et la capture GPS n'attache aucune géométrie (entités fantômes,
    # position NULL). _force_gpkg_geom_types() relit cet attribut pour corriger
    # gpkg_geometry_columns après écriture.
    gdf.attrs["geom_type"] = geom_type
    return gdf


def _force_gpkg_geom_types(path, layer_types: dict) -> None:
    """Force le type géométrie déclaré dans gpkg_geometry_columns.

    pyogrio écrit « GEOMETRY » pour une couche vide. QField/OGR lit le type
    déclaré ici comme source autoritaire : on le réécrit en POINT/POLYGON/…
    pour les couches concernées. Sans effet sur les données (couches vides).
    """
    import sqlite3
    with sqlite3.connect(str(path)) as con:
        cur = con.cursor()
        existing = {r[0] for r in cur.execute(
            "SELECT table_name FROM gpkg_geometry_columns")}
        for layer, gtype in layer_types.items():
            if layer in existing:
                cur.execute(
                    "UPDATE gpkg_geometry_columns SET geometry_type_name=? "
                    "WHERE table_name=?", (gtype.upper(), layer))
        con.commit()


def create_empty_gpkg(path: Path, crs: str = "EPSG:2154") -> None:
    """Crée un GeoPackage vide avec les couches de base.

    Les couches cibles P1/P2 sont créées dynamiquement par
    ``package_qfield_project`` avec le nom du secteur.
    """
    path = Path(path)
    cav = _make_empty_layer(CAVITES_SCHEMA, crs, "Point")
    dol = _make_empty_layer(DOLINES_SCHEMA, crs, "Polygon")
    cav.to_file(path, layer="cavites", driver="GPKG")
    dol.to_file(path, layer="dolines", driver="GPKG")
    _force_gpkg_geom_types(
        path, {"cavites": "POINT", "dolines": "POLYGON"})
