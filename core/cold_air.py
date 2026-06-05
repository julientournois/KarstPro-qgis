# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
# Usage commercial interdit sans autorisation écrite — julien.tournois@gmail.com
# https://polyformproject.org/licenses/noncommercial/1.0.0
"""
karstpro.core.cold_air
----------------------
Calcul de l'indice de piégeage d'air froid (Cold Air Pooling Index) pour
chaque doline, à partir du MNT LiDAR 1 m déjà produit par le pipeline.

Principe physique
-----------------
L'air froid est plus dense que l'air chaud : il s'écoule vers les points bas
et s'accumule dans les dépressions fermées (dolines). Une doline avec :
  - un fort **confinement** (profonde et étroite) piège mieux l'air froid
  - une **courbure négative prononcée** au fond (forme de cuvette) favorise
    l'accumulation
  - un **bassin versant** large par rapport à sa surface reçoit plus d'air
    froid drainé des pentes environnantes

La présence d'un courant d'air (exutoire karstique) se manifeste en hiver
par un ressuage ou une anomalie de gel à l'ouverture — les dolines avec
un fort cold_air_index sont les candidates prioritaires à vérifier.

Index calculé
-------------
cold_air_index ∈ [0, 1]

  cold_air_index = 0.55 × confinement_norm
                 + 0.45 × concavity_norm

  confinement = profondeur_m / diamètre_équivalent
      diamètre_équivalent = 2 × √(surface_m² / π)

  concavity   = max(0, laplacien_MNT_au_centroïde) × résolution²
      valeur positive = forme concave (cuvette, centre plus bas que voisins)
      valeur nulle    = fond plat ou convexe (pas de piège)

Les deux composantes sont normalisées [0, 1] par rapport au 95e percentile
de l'ensemble des dolines du secteur pour éviter l'effet des valeurs extrêmes.

Disponibilité
-------------
Toujours calculé si le MNT existe — pas de dépendance externe.
Résolution native : 1 m (LiDAR IGN).
"""

from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import geopandas as gpd


def compute_cold_air_index(
    dolines: "gpd.GeoDataFrame",
    mnt_path: Path,
    feedback=None,
) -> "gpd.GeoDataFrame":
    """
    Ajoute la colonne ``cold_air_index`` [0–1] aux dolines.

    Parameters
    ----------
    dolines   : GeoDataFrame en EPSG:2154, avec colonnes surface_m2 et profondeur_m
    mnt_path  : chemin vers le raster MNT (GeoTIFF, même CRS que dolines)
    feedback  : QgsProcessingFeedback ou None

    Returns
    -------
    GeoDataFrame avec colonne cold_air_index (float, NaN si géométrie hors MNT)
    """
    import numpy as np
    import rasterio

    def log(msg: str) -> None:
        if feedback:
            feedback.pushInfo(msg)

    dolines = dolines.copy()

    if dolines.empty:
        dolines["cold_air_index"] = float("nan")
        return dolines

    log("Cold air pooling index : lecture MNT 1 m...")

    # ── 1. Lecture MNT et calcul de la courbure (laplacien discret) ──────
    with rasterio.open(mnt_path) as src:
        dem = src.read(1).astype(np.float64)
        transform = src.transform
        res = abs(float(transform.a))          # résolution en mètres (1 m)
        nodata = src.nodata

    if nodata is not None:
        dem[dem == nodata] = np.nan

    # Laplacien par différences finies — valeur positive = concave (cuvette)
    # Pour une cuvette, le centre est plus bas que ses voisins :
    # (N + S + E + W) > 4 × C  →  curvature > 0
    # curv[i,j] = (N + S + E + W − 4×C) / res²
    dem_filled = np.nan_to_num(dem, nan=float(np.nanmedian(dem)))
    pad = np.pad(dem_filled, 1, mode="edge")
    curvature = (
        pad[:-2, 1:-1] + pad[2:, 1:-1] +
        pad[1:-1, :-2] + pad[1:-1, 2:] -
        4.0 * dem_filled
    ) / (res ** 2)
    # Concavité = partie positive (cuvette) ; on ignore les formes convexes
    concavity = np.clip(curvature, 0, None)

    # ── 2. Extraction par centroïde ───────────────────────────────────────
    centroids = dolines.geometry.centroid
    confinements: list[float] = []
    concavities: list[float] = []

    rows_arr, cols_arr = rasterio.transform.rowcol(
        transform,
        [c.x for c in centroids],
        [c.y for c in centroids],
    )

    h, w = dem.shape
    for i, (r, c) in enumerate(zip(rows_arr, cols_arr)):
        # ── Confinement ──────────────────────────────────────────────────
        depth   = float(dolines.iloc[i].get("profondeur_m") or 0)
        surface = float(dolines.iloc[i].get("surface_m2") or 1)
        diameter = 2.0 * np.sqrt(max(surface, 1.0) / np.pi)
        confinements.append(depth / diameter)

        # ── Concavité au centroïde (fenêtre 3×3 pour robustesse) ─────────
        r0, r1 = max(0, r - 1), min(h, r + 2)
        c0, c1 = max(0, c - 1), min(w, c + 2)
        if r0 < h and c0 < w:
            window = concavity[r0:r1, c0:c1]
            concavities.append(float(np.nanmean(window)) if window.size else 0.0)
        else:
            concavities.append(0.0)

    # ── 3. Normalisation [0, 1] par 95e percentile ────────────────────────
    conf_arr = np.array(confinements)
    conc_arr = np.array(concavities)

    def _norm(arr: np.ndarray) -> np.ndarray:
        finite = arr[np.isfinite(arr)]
        if finite.size == 0 or (p95 := np.percentile(finite, 95)) == 0:
            return np.zeros_like(arr)
        return np.clip(arr / p95, 0.0, 1.0)  # type: ignore[no-any-return]

    conf_norm = _norm(conf_arr)
    conc_norm = _norm(conc_arr)

    cold_air = np.round(0.55 * conf_norm + 0.45 * conc_norm, 3)

    dolines["cold_air_index"] = cold_air.tolist()

    valid = int(np.sum(np.isfinite(cold_air)))
    log(
        f"Cold air pooling index OK : {valid}/{len(dolines)} dolines calculées "
        f"(confinement 55 % + concavité MNT 45 %)"
    )
    return dolines


def compute_slope_max_bord(
    dolines: "gpd.GeoDataFrame",
    mnt_path: Path,
    ring_width: float = 5.0,
    feedback=None,
) -> "gpd.GeoDataFrame":
    """
    Ajoute la colonne ``pente_max_bord`` (degrés) : 90e percentile de pente
    mesuré sur l'anneau périphérique de chaque doline.

    Principe physique
    -----------------
    Un versant subvertical (pente > 45–70°) est la signature d'un soutirage
    actif — le fond s'est affaissé brutalement, laissant des parois raides.
    Un effondrement ancien stabilisé présente des bords adoucis (< 20°).
    Sur LiDAR 1 m, cette distinction est discriminante sans ambiguïté.

    Paramètres v2 (ScoringReview 2026)
    -----------------------------------
    ring_width : largeur de l'anneau en mètres de part et d'autre de la
                 bordure extérieure (défaut 5 m, était 3 m).
                 5 m échantillonne mieux les parois de grandes dolines.
    p90        : on utilise le 90e percentile plutôt que le maximum brut.
                 Le max était trop sensible aux artefacts LiDAR ponctuels
                 (arbres en bordure, piquet de clôture) qui faisaient sauter
                 une doline de 35° à 85° sur un seul pixel.
                 Le p90 reste discriminant pour les parois vraiment raides
                 tout en éliminant les outliers isolés.
    """
    import numpy as np
    import rasterio
    from rasterio.features import geometry_mask

    def log(msg: str) -> None:
        if feedback:
            feedback.pushInfo(msg)

    dolines = dolines.copy()

    if dolines.empty:
        dolines["pente_max_bord"] = float("nan")
        return dolines

    log("Pente max bord : calcul du gradient MNT 1 m...")

    with rasterio.open(mnt_path) as src:
        dem = src.read(1).astype(np.float64)
        transform = src.transform
        res = abs(float(transform.a))
        nodata = src.nodata

    if nodata is not None:
        dem[dem == nodata] = np.nan

    dem_filled = np.nan_to_num(dem, nan=float(np.nanmedian(dem)))

    # Gradient sur l'ensemble du raster (calculé une seule fois)
    dy, dx = np.gradient(dem_filled, res)
    slope_deg = np.degrees(np.arctan(np.sqrt(dx ** 2 + dy ** 2)))

    h, w = dem.shape
    orig_x = float(transform.c)   # coin supérieur gauche X
    orig_y = float(transform.f)   # coin supérieur gauche Y

    pentes: list[float] = []
    margin = ring_width + 2 * res  # marge pour capturer l'anneau complet

    for geom in dolines.geometry:
        if geom is None or geom.is_empty:
            pentes.append(float("nan"))
            continue
        try:
            minx, miny, maxx, maxy = geom.bounds

            # Fenêtre pixel avec marge
            col0 = max(0, int((minx - margin - orig_x) / res))
            row0 = max(0, int((orig_y - maxy - margin) / res))
            col1 = min(w, int((maxx + margin - orig_x) / res) + 1)
            row1 = min(h, int((orig_y - miny + margin) / res) + 1)

            if row0 >= row1 or col0 >= col1:
                pentes.append(float("nan"))
                continue

            local_slope = slope_deg[row0:row1, col0:col1]

            # Transform local (coin sup-gauche de la fenêtre)
            local_x0 = orig_x + col0 * res
            local_y0 = orig_y - row0 * res
            local_transform = rasterio.transform.from_origin(
                local_x0, local_y0, res, res
            )

            # Anneau autour de la bordure extérieure
            ring_geom = geom.exterior.buffer(ring_width)
            mask = geometry_mask(
                [ring_geom],
                transform=local_transform,
                invert=True,
                out_shape=local_slope.shape,
            )
            vals = local_slope[mask]
            # p90 : robuste aux artefacts LiDAR ponctuels (arbres, clôtures)
            # tout en restant discriminant pour les parois vraiment raides.
            pentes.append(float(np.nanpercentile(vals, 90)) if vals.size > 0 else float("nan"))
        except Exception:
            pentes.append(float("nan"))

    dolines["pente_max_bord"] = pentes
    import math
    valid = sum(1 for p in pentes if not math.isnan(p))
    log(f"Pente max bord OK : {valid}/{len(dolines)} dolines calculées (p90, anneau {ring_width} m)")
    return dolines
