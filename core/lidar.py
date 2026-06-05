# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
# Usage commercial interdit sans autorisation écrite — julien.tournois@gmail.com
# https://polyformproject.org/licenses/noncommercial/1.0.0
from __future__ import annotations

import requests
from pathlib import Path
from typing import TYPE_CHECKING, List, Dict, Tuple

if TYPE_CHECKING:
    import geopandas as gpd

# Heavy scientific imports (numpy, rasterio, geopandas, whitebox) are deferred
# to inside each function. QGIS sets sys.stderr=None during plugin load, which
# crashes C-extensions that emit deprecation warnings. Lazy imports avoid this.

# Lazy singleton — initialized on first use to avoid sys.stdout=None at QGIS startup
_wbt = None


def _get_wbt():
    """Returns a WhiteboxTools instance, re-creating it if necessary.

    verbose_mode is left at its default (True) so WBT writes progress to
    stdout. Our _SafeStream in __init__.py absorbs that output silently.
    Setting verbose_mode=False causes WBT to suppress its own output in a
    way that can break file creation inside QGIS's Python environment.

    On Windows, WBT spawns a subprocess for each tool call. We patch
    subprocess.Popen to add CREATE_NO_WINDOW so the terminal never flashes.
    """
    global _wbt
    if _wbt is None:
        import whitebox
        _patch_subprocess_no_window()
        _wbt = whitebox.WhiteboxTools()
    return _wbt


def _patch_subprocess_no_window() -> None:
    """
    Sur Windows, force CREATE_NO_WINDOW sur tous les appels subprocess.Popen
    du processus courant, évitant le flash de fenêtres console lors des appels
    à WhiteboxTools et PDAL.
    Sans effet sur Linux/macOS. Idempotent — appliqué au plus une fois.
    """
    import sys
    import subprocess

    if sys.platform != "win32":
        return
    if getattr(subprocess.Popen.__init__, "_patched_no_window", False):
        return

    _original_popen_init = subprocess.Popen.__init__

    def _popen_no_window(self, *args, **kwargs):
        kwargs.setdefault("creationflags", 0)
        kwargs["creationflags"] |= subprocess.CREATE_NO_WINDOW
        _original_popen_init(self, *args, **kwargs)

    _popen_no_window._patched_no_window = True  # type: ignore[attr-defined]
    subprocess.Popen.__init__ = _popen_no_window  # type: ignore[method-assign]


# IGN LiDAR HD tile catalog — WFS endpoint (data.geopf.fr, migrated 2023-2024)
# wxs.ign.fr is dead; download URLs embed a bloc+date segment that changes at each
# IGN re-delivery and cannot be hardcoded — must be resolved via WFS.
_IGN_WFS_URL = "https://data.geopf.fr/wfs/ows"
_IGN_WFS_TYPENAME = "IGNF_NUAGES-DE-POINTS-LIDAR-HD:dalle"


def bbox_to_ign_tiles(bbox_l93: tuple) -> List[Dict[str, str]]:
    """Queries the IGN WFS catalog and returns LIDAR HD tile download URLs for a bbox.

    IGN migrated from wxs.ign.fr to data.geopf.fr in 2023-2024. Download URLs
    now contain a bloc+date segment (e.g. NUALHD_1-0__LAZ_LAMB93_IR_2025-03-20)
    that varies by region and delivery batch — it cannot be computed from coordinates.
    The WFS catalog always returns the current, valid URL for each tile.

    Args:
        bbox_l93: Tuple (xmin, ymin, xmax, ymax) in Lambert-93 projection (metres)

    Returns:
        List of dicts with 'url' and 'filename' keys for each 1km tile covering the bbox

    Raises:
        RuntimeError: If the WFS request fails
        ValueError: If no tiles are found for the given bbox
    """
    xmin, ymin, xmax, ymax = bbox_l93
    params = {
        "SERVICE": "WFS",
        "REQUEST": "GetFeature",
        "VERSION": "2.0.0",
        "TYPENAMES": _IGN_WFS_TYPENAME,
        "outputFormat": "application/json",
        "BBOX": f"{xmin},{ymin},{xmax},{ymax},EPSG:2154",
        "SRSNAME": "EPSG:2154",
    }
    resp = requests.get(_IGN_WFS_URL, params=params, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(
            f"IGN WFS catalog request failed: HTTP {resp.status_code}\n{resp.text[:300]}"
        )
    features = resp.json().get("features", [])
    if not features:
        raise ValueError(
            f"Aucune dalle LiDAR HD IGN trouvée pour la bbox {bbox_l93}. "
            "Vérifiez que la zone est couverte par le LiDAR HD IGN."
        )

    tiles = []
    for feat in features:
        props = feat.get("properties", {})
        url = props.get("url") or props.get("telechargement_url") or props.get("download_url")
        if not url:
            # Fallback: reconstruct from nom_dalle if direct URL is not in properties
            nom = props.get("nom_dalle", "")
            if nom:
                url = f"https://data.geopf.fr/telechargement/download/{nom}"
        if not url:
            continue
        filename = url.split("/")[-1]
        tiles.append({"url": url, "filename": filename})

    if not tiles:
        raise ValueError(
            "Le catalogue WFS IGN a retourné des dalles mais sans URL de téléchargement. "
            "Vérifiez la structure de la réponse WFS."
        )
    return tiles


def _download_with_resume(url: str, dest: Path, max_retries: int = 15,
                          chunk_size: int = 512 * 1024,
                          progress_cb=None) -> None:
    """Downloads a file with automatic resume on connection drop (HTTP Range).

    Retries up to max_retries times with exponential backoff.
    The partial file is kept between retries so each attempt resumes where
    the previous one left off (HTTP Range header).

    Args:
        url: URL to download
        dest: Destination path (partial file kept between retries)
        max_retries: Maximum number of retry attempts (default 15)
        chunk_size: Download chunk size in bytes (default 512 KB)

    Raises:
        RuntimeError: If download fails after all retries
    """
    import time

    # HTTP status codes worth retrying (server-side transient errors)
    RETRYABLE_HTTP = {429, 500, 502, 503, 504}

    for attempt in range(1, max_retries + 1):
        existing = dest.stat().st_size if dest.exists() else 0
        headers = {"Range": f"bytes={existing}-"} if existing > 0 else {}

        # ── Establish connection ──────────────────────────────────────────
        try:
            resp = requests.get(
                url, headers=headers, stream=True,
                timeout=(30, 180),  # (connect_timeout, read_timeout)
            )
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as exc:
            if attempt == max_retries:
                raise RuntimeError(
                    f"Connexion impossible après {max_retries} tentatives : {exc}"
                ) from exc
            time.sleep(min(2 ** attempt, 60))
            continue

        # ── Handle HTTP status ────────────────────────────────────────────
        if resp.status_code == 416:
            # Range out of bounds — file already complete
            return

        if resp.status_code in RETRYABLE_HTTP:
            # Server overloaded / bad gateway — wait and retry
            if attempt == max_retries:
                raise RuntimeError(
                    f"Échec téléchargement {url} : HTTP {resp.status_code} "
                    f"après {max_retries} tentatives"
                )
            wait = min(2 ** attempt, 60)
            time.sleep(wait)
            continue

        if resp.status_code == 200 and existing > 0:
            # Server doesn't support Range — restart from scratch
            existing = 0
            dest.unlink(missing_ok=True)

        if resp.status_code not in (200, 206):
            raise RuntimeError(
                f"Échec téléchargement {url} : HTTP {resp.status_code}"
            )

        # ── Stream to disk ────────────────────────────────────────────────
        mode = "ab" if existing > 0 else "wb"
        try:
            downloaded = existing
            last_reported = existing
            REPORT_EVERY = 20 * 1024 * 1024  # log toutes les 20 MB
            with open(dest, mode) as f:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb and downloaded - last_reported >= REPORT_EVERY:
                            progress_cb(downloaded)
                            last_reported = downloaded
            return  # success
        except (requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as exc:
            if attempt == max_retries:
                raise RuntimeError(
                    f"Téléchargement échoué après {max_retries} tentatives : {exc}"
                ) from exc
            # Partial file kept on disk — next attempt resumes via Range
            wait = min(2 ** attempt, 60)
            time.sleep(wait)


def download_lidar_tiles(tiles: List[Dict], dest_dir: Path,
                         max_retries: int = 15,
                         max_workers: int = 3,
                         feedback=None) -> List[Path]:
    """Downloads LAZ tiles in parallel with automatic resume on connection drop.

    Args:
        tiles: List of dicts with 'url' and 'filename' keys
        dest_dir: Destination directory for downloaded tiles
        max_retries: Maximum retry attempts per tile (default 15)
        max_workers: Parallel download threads (default 3)
        feedback: Optional QgsProcessingFeedback for progress messages

    Returns:
        List of Path objects for downloaded files (same order as input)

    Raises:
        RuntimeError: If any tile fails after all retries
    """
    import concurrent.futures
    import threading

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    completed = [0]
    lock = threading.Lock()

    def _log(msg: str) -> None:
        if feedback:
            feedback.pushInfo(msg)

    def _process_tile(tile: Dict, stagger_idx: int = 0) -> Path:
        import time as _time
        # Stagger thread starts to avoid hammering the CDN simultaneously
        if stagger_idx > 0:
            _time.sleep(stagger_idx * 0.5)

        dest = dest_dir / tile["filename"]
        filename = tile["filename"]

        # Skip if already fully downloaded
        try:
            head = requests.head(tile["url"], timeout=10)
            remote_size = int(head.headers.get("Content-Length", 0))
            if dest.exists() and remote_size > 0 and dest.stat().st_size == remote_size:
                with lock:
                    completed[0] += 1
                    _log(f"  [{completed[0]}/{len(tiles)}] {filename} — cache OK")
                return dest  # type: ignore[no-any-return]
        except Exception:
            pass  # HEAD failed — fall through to download

        size_mb = dest.stat().st_size / 1024 / 1024 if dest.exists() else 0
        if size_mb > 0:
            _log(f"  Reprise {filename} ({size_mb:.0f} MB déjà téléchargés)...")
        else:
            _log(f"  Démarrage {filename}...")

        def _progress(downloaded_bytes: int) -> None:
            _log(f"    {filename} — {downloaded_bytes / 1024 / 1024:.0f} MB téléchargés...")

        _download_with_resume(tile["url"], dest, max_retries=max_retries,
                              progress_cb=_progress)

        with lock:
            completed[0] += 1
            final_mb = dest.stat().st_size / 1024 / 1024
            _log(f"  [{completed[0]}/{len(tiles)}] {filename} — OK ({final_mb:.0f} MB)")

        return dest  # type: ignore[no-any-return]

    # Single tile — skip thread pool overhead
    if len(tiles) == 1:
        return [_process_tile(tiles[0])]

    results: List[Path | None] = [None] * len(tiles)  # filled before return
    failed: List[Dict] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(_process_tile, tile, i % max_workers): i
            for i, tile in enumerate(tiles)
        }
        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            tile = tiles[idx]
            try:
                results[idx] = future.result()
            except RuntimeError as exc:
                failed.append({"tile": tile, "error": str(exc)})
                results[idx] = None
                _log(f"  ⚠ Échec définitif : {tile['filename']} — {exc}")

    if failed:
        urls = "\n".join(f"  {f['tile']['url']}" for f in failed)
        filenames = ", ".join(f['tile']['filename'] for f in failed)
        raise RuntimeError(
            f"{len(failed)} dalle(s) impossible(s) à télécharger après {max_retries} "
            f"tentatives (CDN IGN instable) :\n{filenames}\n\n"
            f"Solution : télécharger manuellement via le fichier dalles_a_telecharger.txt "
            f"dans le dossier laz, déposer les .copc.laz dans ce même dossier, "
            f"puis relancer.\n\nURLs :\n{urls}"
        )

    return [r for r in results if r is not None]


def _find_pdal_exe() -> str:
    """Locates the pdal executable, preferring the QGIS bundled version.

    Résolution dans l'ordre :
    1. QgsApplication.prefixPath() / bin / pdal.exe  (QGIS en cours d'exécution)
    2. shutil.which("pdal")  (pdal dans le PATH système)
    """
    import shutil

    # 1. Chemin dynamique via QgsApplication (fonctionne sur toute installation QGIS)
    try:
        from qgis.core import QgsApplication
        prefix = Path(QgsApplication.prefixPath())
        candidate = prefix / "bin" / "pdal.exe"
        if candidate.exists():
            return str(candidate)
    except Exception:
        pass  # hors QGIS (tests unitaires) — continuer vers shutil.which

    # 2. pdal dans le PATH système (Linux, macOS, Windows avec pdal installé séparément)
    found = shutil.which("pdal")
    if found:
        return found

    raise RuntimeError(
        "pdal.exe introuvable. Vérifiez que QGIS est correctement installé "
        "ou que pdal est disponible dans le PATH."
    )


def generate_mnt(laz_files: List[Path], output_tif: Path, resolution: float = 1.0) -> Path:
    """Generates a 1m GeoTIFF DEM from LAZ files via the PDAL CLI.

    Uses the pdal.exe bundled with QGIS (no Python pdal bindings required).
    Filters to ground classification (Class 2), merges all input tiles, and
    writes a LZW-compressed GeoTIFF.

    Args:
        laz_files: List of LAZ/COPC file paths
        output_tif: Output GeoTIFF path
        resolution: Pixel resolution in metres (default 1.0)

    Returns:
        Path to generated GeoTIFF

    Raises:
        ValueError: If laz_files is empty
        RuntimeError: If PDAL CLI fails or pdal.exe is not found
    """
    import json
    import subprocess
    import tempfile

    if not laz_files:
        raise ValueError("Aucun fichier LAZ fourni")
    output_tif = Path(output_tif)
    output_tif.parent.mkdir(parents=True, exist_ok=True)

    # Skip if MNT already exists (allows restarting after a crash without reprocessing)
    if output_tif.exists() and output_tif.stat().st_size > 0:
        return output_tif

    pdal_exe = _find_pdal_exe()
    # Use forward slashes — PDAL on Windows sometimes chokes on backslashes
    inputs = [str(f).replace("\\", "/") for f in laz_files]
    out_str = str(output_tif).replace("\\", "/")

    # readers.las handles .laz and .copc.laz files; faster than readers.copc
    # for local files because it reads sequentially without spatial indexing overhead.
    pipeline_def = {
        "pipeline": [
            *[{"type": "readers.las", "filename": f} for f in inputs],
            *([ {"type": "filters.merge"} ] if len(inputs) > 1 else []),
            {"type": "filters.range", "limits": "Classification[2:2]"},
            {
                "type": "writers.gdal",
                "filename": out_str,
                "resolution": resolution,
                "output_type": "mean",
                "gdalopts": "COMPRESS=LZW",
                "override_srs": "EPSG:2154",  # force CRS in output GeoTIFF
            },
        ]
    }

    # Write pipeline to a temp file and run pdal pipeline
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                     delete=False, encoding="utf-8") as fp:
        json.dump(pipeline_def, fp)
        pipeline_path = fp.name

    # CREATE_NO_WINDOW évite le flash de fenêtre console sur Windows
    _no_window = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

    try:
        result = subprocess.run(
            [pdal_exe, "pipeline", pipeline_path],
            capture_output=True, text=True,
            timeout=7200,  # 2h max — large tiles at 1m resolution can take 30-60 min
            creationflags=_no_window,
        )
    finally:
        Path(pipeline_path).unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"PDAL pipeline failed (code {result.returncode}):\n"
            f"{result.stderr.strip()}"
        )
    return output_tif


def detect_dolines(mnt_path: Path, work_dir: Path, min_area_m2: float = 10.0):
    """Detects sinkholes by diffing original DEM vs filled DEM (WhiteboxTools).

    Args:
        mnt_path: Path to input MNT GeoTIFF
        work_dir: Working directory for intermediate files
        min_area_m2: Minimum sinkhole area in m² (default 10.0)

    Returns:
        GeoDataFrame with columns geometry, surface_m2, profondeur_m
    """
    import numpy as np
    import rasterio
    from rasterio.features import shapes
    import geopandas as gpd
    from shapely.geometry import shape

    work_dir = Path(work_dir)
    mnt_filled = work_dir / "mnt_filled.tif"

    wbt = _get_wbt()
    wbt.set_verbose_mode(True)  # capture output for debugging
    ret = wbt.fill_depressions(str(mnt_path), str(mnt_filled))
    if ret != 0 or not Path(mnt_filled).exists():
        raise RuntimeError(
            f"WhiteboxTools fill_depressions a échoué (code {ret}). "
            f"Fichier attendu : {mnt_filled}\n"
            "Vérifiez que whitebox est correctement installé : "
            "'python -m pip install whitebox' dans QGIS Python 3.12."
        )

    with rasterio.open(mnt_path) as src_orig:
        orig = src_orig.read(1).astype(np.float32)
        nodata = src_orig.nodata
        transform = src_orig.transform
        # Use EPSG authority string — rasterio CRS objects can produce srs_id=99999
        # in GeoPackage when passed directly to geopandas.
        # PDAL may omit CRS metadata; fall back to EPSG:2154 (all IGN L93 data).
        raw_crs = src_orig.crs
        if raw_crs is not None:
            epsg_code = raw_crs.to_epsg()
            crs_str = f"EPSG:{epsg_code}" if epsg_code else "EPSG:2154"
        else:
            crs_str = "EPSG:2154"
    with rasterio.open(mnt_filled) as src_fill:
        filled = src_fill.read(1).astype(np.float32)

    # Mask out nodata pixels
    valid = np.ones(orig.shape, dtype=bool)
    if nodata is not None:
        valid = (orig != nodata) & (filled != nodata)

    diff = filled - orig  # positive = depression (filled higher than original)

    # Binary mask of depression pixels (depth > 0.1 m to catch shallow karst)
    dep_mask = (diff > 0.1) & valid

    if not dep_mask.any():
        return gpd.GeoDataFrame(
            columns=["geometry", "surface_m2", "profondeur_m"], crs=crs_str
        )

    # shapes() on a BINARY uint8 raster groups connected pixels into polygons.
    # Using float32 would give one polygon per unique value (i.e. one per pixel).
    dep_binary = dep_mask.astype(np.uint8)
    geoms = []
    for geom_dict, val in shapes(dep_binary, mask=dep_mask, transform=transform):
        if val != 1:
            continue
        poly = shape(geom_dict)
        geoms.append({"geometry": poly})

    if not geoms:
        return gpd.GeoDataFrame(
            columns=["geometry", "surface_m2", "profondeur_m"], crs=crs_str
        )

    gdf = gpd.GeoDataFrame(geoms, crs=crs_str)
    gdf["surface_m2"] = gdf.geometry.area

    # Altitude du centroïde depuis le MNT original (avant remplissage)
    altitudes = []
    for geom in gdf.geometry:
        c = geom.centroid
        try:
            row_idx, col_idx = rasterio.transform.rowcol(transform, c.x, c.y)
            if 0 <= row_idx < orig.shape[0] and 0 <= col_idx < orig.shape[1]:
                val = float(orig[row_idx, col_idx])
                altitudes.append(round(val, 1) if (nodata is None or val != nodata) else None)
            else:
                altitudes.append(None)
        except Exception:
            altitudes.append(None)
    gdf["altitude_m"] = altitudes

    # Filter by minimum area first (cheap)
    gdf = gdf[gdf["surface_m2"] > min_area_m2].reset_index(drop=True)

    if gdf.empty:
        return gdf

    # Compute representative depth per polygon using rasterio.features.rasterize
    # to find pixels belonging to each polygon, then take the max diff value.
    from rasterio.features import rasterize
    profondeurs = []
    for geom in gdf.geometry:
        poly_mask = rasterize(
            [(geom.__geo_interface__, 1)],
            out_shape=diff.shape,
            transform=transform,
            fill=0,
            dtype=np.uint8,
        ).astype(bool)
        vals = diff[poly_mask & valid]
        profondeurs.append(round(float(vals.max()) if vals.size > 0 else 0.0, 2))
    gdf["profondeur_m"] = profondeurs

    return gdf


def compute_bassin_versant(dolines: "gpd.GeoDataFrame", flow_acc_path: Path) -> "gpd.GeoDataFrame":
    """Calcule la surface du bassin versant amont de chaque doline (m²).

    Lit le raster de flow accumulation D8 (1 cellule = 1 m²) et extrait la
    valeur maximale à l'intérieur de chaque polygone de doline.  Cette valeur
    représente la surface drainée vers la doline depuis l'amont.

    Classifie ensuite le type de doline :
      - ``"perte"``        : bassin > seuil_perte_m2   (captage massif, chenal actif)
      - ``"doline-perte"`` : bassin > seuil_doline_perte_m2  (captage modéré)
      - ``"doline"``       : bassin modeste (dépression fermée isolée)

    Les seuils par défaut sont indicatifs pour un karst sous couverture (Barrois) :
      - > 20 000 m² (2 ha)  → perte
      - > 5 000 m²  (0.5 ha) → doline-perte
      - ≤ 5 000 m²           → doline

    Args:
        dolines: GeoDataFrame des polygones de dolines (EPSG:2154)
        flow_acc_path: Chemin vers le raster flow_acc.tif (WBT d8_flow_accumulation)

    Returns:
        GeoDataFrame enrichi des colonnes ``bassin_versant_m2`` et ``type_doline``
    """
    import numpy as np
    import rasterio
    from rasterio.features import rasterize

    SEUIL_PERTE       = 20_000   # m²
    SEUIL_DOLINE_PERTE = 5_000   # m²

    dolines = dolines.copy()

    if not Path(flow_acc_path).exists():
        dolines["bassin_versant_m2"] = np.nan
        dolines["type_doline"]       = "doline"
        return dolines

    bassins = []
    types   = []

    with rasterio.open(flow_acc_path) as src:
        flow = src.read(1).astype(np.float64)
        nodata = src.nodata
        transform = src.transform
        if nodata is not None:
            flow[flow == nodata] = 0.0

        for geom in dolines.geometry:
            if geom is None or geom.is_empty:
                bassins.append(np.nan)
                types.append("doline")
                continue
            try:
                mask = rasterize(
                    [(geom.__geo_interface__, 1)],
                    out_shape=flow.shape,
                    transform=transform,
                    fill=0,
                    dtype=np.uint8,
                ).astype(bool)
                vals = flow[mask]
                # max flow acc inside polygon = upstream drainage area in cells (= m²)
                bv = float(vals.max()) if vals.size > 0 else 0.0
            except Exception:
                bv = 0.0

            bassins.append(round(bv, 0))
            if bv >= SEUIL_PERTE:
                types.append("perte")
            elif bv >= SEUIL_DOLINE_PERTE:
                types.append("doline-perte")
            else:
                types.append("doline")

    dolines["bassin_versant_m2"] = bassins
    dolines["type_doline"]       = types
    return dolines


def compute_hydrology(mnt_path: Path, work_dir: Path) -> Tuple:
    """Computes D8 stream network and absorption points.

    Args:
        mnt_path: Path to input MNT GeoTIFF
        work_dir: Working directory for intermediate files

    Returns:
        Tuple of (reseau_gdf, absorptions_gdf) as GeoDataFrames
    """
    import numpy as np
    import rasterio
    from rasterio.features import shapes
    import geopandas as gpd
    from shapely.geometry import shape, Point

    work_dir = Path(work_dir)
    flow_acc = work_dir / "flow_acc.tif"
    streams = work_dir / "streams.tif"
    sinks_path = work_dir / "sinks.tif"

    wbt = _get_wbt()
    wbt.d8_flow_accumulation(str(mnt_path), str(flow_acc))
    wbt.extract_streams(str(flow_acc), str(streams), threshold=1000)
    wbt.sink(str(mnt_path), str(sinks_path))

    with rasterio.open(streams) as src:
        stream_data = src.read(1)
        transform = src.transform
        raw_crs = src.crs
        if raw_crs is not None:
            epsg = raw_crs.to_epsg()
            crs_str = f"EPSG:{epsg}" if epsg else "EPSG:2154"
        else:
            crs_str = "EPSG:2154"

    stream_mask = (stream_data > 0).astype(np.uint8)
    stream_geoms = [
        shape(g)
        for g, v in shapes(stream_mask, mask=stream_mask, transform=transform)
        if v == 1
    ]
    reseau = gpd.GeoDataFrame(geometry=stream_geoms, crs=crs_str)

    with rasterio.open(sinks_path) as src:
        sink_data = src.read(1)
        sink_transform = src.transform
    sink_rows, sink_cols = np.where(sink_data > 0)
    sink_points = [
        Point(sink_transform * (int(c), int(r)))
        for r, c in zip(sink_rows, sink_cols)
    ]
    absorptions = gpd.GeoDataFrame(geometry=sink_points, crs=crs_str)

    return reseau, absorptions


def generate_contours(mnt_path: Path, interval: float = 5.0,
                      index_interval: float = 10.0) -> "gpd.GeoDataFrame":
    """Génère les courbes de niveau d'un MNT.

    Args:
        mnt_path       : raster MNT (GeoTIFF, EPSG:2154).
        interval       : équidistance des courbes en mètres (ex. 5.0).
        index_interval : équidistance des courbes maîtresses (ex. 10.0).

    Returns:
        GeoDataFrame (LineString, EPSG:2154) avec colonnes :
          - ELEV      : altitude de la courbe (m)
          - maitresse : 1 si ELEV multiple de index_interval, sinon 0

    Utilise gdal.ContourGenerateEx (présent dans l'environnement QGIS).
    """
    import tempfile
    import geopandas as gpd
    from osgeo import gdal, ogr, osr

    gdal.UseExceptions()
    ds = gdal.Open(str(mnt_path))
    if ds is None:
        raise RuntimeError(f"MNT illisible : {mnt_path}")
    band = ds.GetRasterBand(1)
    nodata = band.GetNoDataValue()

    tmp_dir = Path(tempfile.mkdtemp(prefix="kp_contours_"))
    tmp_gpkg = tmp_dir / "contours.gpkg"

    drv = ogr.GetDriverByName("GPKG")
    out_ds = drv.CreateDataSource(str(tmp_gpkg))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(2154)
    lyr = out_ds.CreateLayer("contours", srs, ogr.wkbLineString)
    lyr.CreateField(ogr.FieldDefn("ELEV", ogr.OFTReal))

    opts = [f"LEVEL_INTERVAL={interval}", "ELEV_FIELD=0"]
    if nodata is not None:
        opts.append(f"NODATA={nodata}")
    gdal.ContourGenerateEx(band, lyr, options=opts)

    out_ds = None  # flush
    ds = None

    g = gpd.read_file(tmp_gpkg, layer="contours")
    if g.crs is None:
        g = g.set_crs("EPSG:2154", allow_override=True)
    g = g[g.geometry.notna() & (~g.geometry.is_empty)].copy()
    if "ELEV" not in g.columns:
        # selon les versions, le champ peut sortir en minuscules
        for c in g.columns:
            if c.lower() == "elev":
                g = g.rename(columns={c: "ELEV"})
                break
    import numpy as np
    g["maitresse"] = (
        np.isclose(np.remainder(g["ELEV"].to_numpy(dtype="float64"),
                                index_interval), 0.0, atol=1e-6)
        | np.isclose(np.remainder(g["ELEV"].to_numpy(dtype="float64"),
                                  index_interval), index_interval, atol=1e-6)
    ).astype(int)
    return g.reset_index(drop=True)
