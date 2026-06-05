# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
# Usage commercial interdit sans autorisation écrite — julien.tournois@gmail.com
# https://polyformproject.org/licenses/noncommercial/1.0.0
import geopandas as gpd
import pandas as pd


def merge_layers(existing: gpd.GeoDataFrame,
                 incoming: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Concatène deux couches (cavités), en alignant CRS et colonnes."""
    if not incoming.crs or not existing.crs:
        pass  # au moins un CRS absent — on fait confiance à existing
    elif incoming.crs != existing.crs:
        incoming = incoming.to_crs(existing.crs)
    combined = pd.concat([existing, incoming], ignore_index=True)
    return gpd.GeoDataFrame(combined, crs=existing.crs)


def deduplicate_by_proximity(gdf: gpd.GeoDataFrame,
                              threshold_m: float = 10.0) -> gpd.GeoDataFrame:
    """Supprime les doublons à moins de threshold_m l'un de l'autre. Garde le 1er."""
    if len(gdf) <= 1:
        return gdf
    keep = [True] * len(gdf)
    geoms = list(gdf.geometry)
    for i in range(len(geoms)):
        if not keep[i]:
            continue
        for j in range(i + 1, len(geoms)):
            if not keep[j]:
                continue
            if geoms[i].distance(geoms[j]) < threshold_m:
                keep[j] = False
    return gdf[keep].reset_index(drop=True)


def select_promotable(buffer_gdf: gpd.GeoDataFrame,
                      inventory_gdf: "gpd.GeoDataFrame | None",
                      threshold_m: float = 10.0):
    """Partitionne les cavités tampon en (à ajouter, déjà connues).

    Une cavité tampon est considérée déjà présente dans l'inventaire si :
      - sa ``reference`` (non vide) correspond à une référence de l'inventaire
        (clé d'identité forte), ou à défaut
      - elle est à moins de ``threshold_m`` d'une cavité de l'inventaire.

    Retourne ``(to_add, skipped)`` : deux listes d'index de ``buffer_gdf``.
    Les deux quittent le tampon (sémantique « déplacer ») ; seules les
    ``to_add`` sont écrites dans l'inventaire.
    """
    to_add, skipped = [], []
    inv_refs = set()
    inv_geoms = []
    if inventory_gdf is not None and len(inventory_gdf):
        if "reference" in inventory_gdf.columns:
            inv_refs = {
                str(r).strip() for r in inventory_gdf["reference"]
                if r is not None and str(r).strip()
            }
        inv_geoms = [g for g in inventory_gdf.geometry if g is not None]

    for idx, row in buffer_gdf.iterrows():
        ref = str(row.get("reference") or "").strip()
        is_dup = False
        if ref and ref in inv_refs:
            is_dup = True
        else:
            geom = row.geometry
            if geom is not None:
                for g in inv_geoms:
                    if geom.distance(g) < threshold_m:
                        is_dup = True
                        break
        (skipped if is_dup else to_add).append(idx)
    return to_add, skipped


def _last3(coord) -> str:
    """3 derniers chiffres de la partie entière d'une coordonnée (zfill)."""
    return str(abs(int(coord)))[-3:].zfill(3)


def build_reference(feature_id, x, y) -> str:
    """Référence unique au format Karst Entry : ``{fid}-{last3X}{last3Y}``.

    Ex. fid=1, x=543210, y=4891234 → '1-210234'. Copié à l'identique de Karst
    Entry pour que les références auto soient cohérentes entre les deux outils.
    """
    return f"{feature_id}-{_last3(x)}{_last3(y)}"


_ADMIN_FIELDS = ("commune", "code_insee", "code_postal", "departement",
                 "code_dept")


def _fetch_commune_with_contour(lat, lon, timeout=3.0):
    """Géocodage inverse via geo.api.gouv.fr (point-dans-polygone communal).

    Miroir de Karst Entry. Retourne ``(admin_dict|None, polygon|None)`` :
    le dict commune/code_insee/code_postal/departement/code_dept, et le polygone
    communal (shapely) pour le cache. ``(None, None)`` en cas d'échec (réseau,
    hors France, réponse vide). Ne lève jamais d'exception."""
    import json
    import urllib.parse
    import urllib.request
    params = urllib.parse.urlencode({
        "lat": f"{lat:.6f}", "lon": f"{lon:.6f}",
        "fields": "nom,code,codesPostaux,departement,contour", "format": "json",
    })
    url = f"https://geo.api.gouv.fr/communes?{params}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None, None
    if not data:
        return None, None
    c = data[0]
    cps = c.get("codesPostaux") or []
    dep = c.get("departement") or {}
    admin = {
        "commune":     c.get("nom", ""),
        "code_insee":  c.get("code", ""),
        "code_postal": cps[0] if cps else "",
        "departement": dep.get("nom", ""),
        "code_dept":   dep.get("code", ""),
    }
    poly = None
    contour = c.get("contour")
    if contour:
        try:
            from shapely.geometry import shape
            poly = shape(contour)
        except Exception:
            poly = None
    return admin, poly


def make_cached_geocoder(fetch=None):
    """Géocodeur (lat, lon) -> dict|None avec cache de polygones communaux.

    Pour un lot de cavités groupées (cas terrain typique : 1-2 communes), une
    seule requête réseau par commune au lieu d'une par cavité. Exact : test
    point-dans-polygone sur les contours déjà résolus avant tout appel réseau.

    ``fetch`` : callable ``(lat, lon) -> (admin_dict|None, polygon|None)``,
    injecté pour les tests (défaut : ``_fetch_commune_with_contour``)."""
    from shapely.geometry import Point as _Point
    if fetch is None:
        fetch = _fetch_commune_with_contour
    cache = []  # [(polygon, admin_dict)]

    def geocode(lat, lon):
        pt = _Point(lon, lat)  # x=lon, y=lat
        for poly, admin in cache:
            if poly is not None and poly.contains(pt):
                return admin
        admin, poly = fetch(lat, lon)
        if admin is None:
            return None
        cache.append((poly, admin))
        return admin

    return geocode


def build_promotion_gdf(buffer_gdf, to_add_idx, target_crs="EPSG:2154",
                        geocoder=None, ref_start=1):
    """Construit le GeoDataFrame des cavités à insérer dans l'inventaire.

    Promotion **1:1** (schéma v1.2.0 : cavites aligné sur cavites_connues) :
    toutes les colonnes (hors géométrie) sont recopiées telles quelles, sans
    repli dans ``comment``. La ``reference`` vide est auto-générée au format
    Karst Entry ``{fid}-{last3X}{last3Y}`` (fid = ``ref_start`` + rang, calculé
    sur les coordonnées L93 natives). Si ``geocoder`` est fourni, la
    localisation admin (commune/code_*) est résolue par géocodage inverse WGS84.
    La géométrie est reprojetée vers ``target_crs``."""
    def _clean(v):
        if v is None:
            return None
        try:
            if pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return v

    geom_col = buffer_gdf.geometry.name
    cols = [c for c in buffer_gdf.columns if c != geom_col]

    # Localisation admin par géocodage inverse (position WGS84).
    admin = [None] * len(to_add_idx)
    if geocoder is not None and len(to_add_idx):
        try:
            wgs = buffer_gdf.loc[to_add_idx].to_crs("EPSG:4326")
            for i, geom in enumerate(wgs.geometry):
                if geom is not None and not geom.is_empty:
                    admin[i] = geocoder(geom.y, geom.x)  # lat=y, lon=x
        except Exception:
            pass

    rows, geoms = [], []
    for i, idx in enumerate(to_add_idx):
        row = buffer_gdf.loc[idx]
        rec = {c: _clean(row.get(c)) for c in cols}
        # Référence auto si vide, sur coordonnées L93 natives.
        if not rec.get("reference") and row.geometry is not None:
            rec["reference"] = build_reference(
                ref_start + i, row.geometry.x, row.geometry.y)
        if admin[i]:
            for k in _ADMIN_FIELDS:
                v = admin[i].get(k)
                if v:
                    rec[k] = v
        rows.append(rec)
        geoms.append(row.geometry)
    gdf = gpd.GeoDataFrame(rows, geometry=geoms,
                           crs=buffer_gdf.crs or "EPSG:2154")
    if (target_crs is not None and gdf.crs is not None
            and str(gdf.crs) != str(target_crs)):
        gdf = gdf.to_crs(target_crs)
    return gdf


def find_inventory_layer(gpkg_path, preferred: str = "Inventaire Cavités",
                         exclude=("cavites",)):
    """Nom de la couche inventaire dans un GeoPackage.

    Ordre : ``preferred`` puis ``cavites_connues`` si elles portent le noyau
    cavite, sinon la première couche features avec ``name`` + ``reference``.
    Les couches listées dans ``exclude`` (par défaut le tampon ``cavites``) sont
    ignorées — sans quoi, dans le gpkg principal, on détecterait le tampon
    lui-même comme inventaire et on y réinjecterait ses propres points.
    ``None`` si aucune ne convient.

    Lecture via sqlite (pas de dépendance fiona/pyogrio pour le listing)."""
    import sqlite3
    exclude_l = {e.lower() for e in exclude}
    with sqlite3.connect(str(gpkg_path)) as con:
        cur = con.cursor()
        try:
            tables = [r[0] for r in cur.execute(
                "SELECT table_name FROM gpkg_contents WHERE data_type='features'")]
        except sqlite3.Error:
            return None

        def has_core(t):
            cols = {r[1] for r in cur.execute(f'PRAGMA table_info("{t}")')}
            return {"name", "reference"}.issubset(cols)

        for cand in (preferred, "cavites_connues"):
            if (cand in tables and cand.lower() not in exclude_l
                    and has_core(cand)):
                return cand
        for t in tables:
            if t.lower() in exclude_l:
                continue
            if has_core(t):
                return t
    return None


def find_tracages_layer(gpkg_path, preferred: str = "Inventaire Traçages"):
    """Nom de la couche traçages dans un GeoPackage : ``preferred`` puis
    ``tracages``, sinon la première couche portant un champ traçage typique
    (``colorant`` ou ``point_injection``). ``None`` si aucune ne convient."""
    import sqlite3
    markers = {"colorant", "point_injection", "point_sortie"}
    with sqlite3.connect(str(gpkg_path)) as con:
        cur = con.cursor()
        try:
            tables = [r[0] for r in cur.execute(
                "SELECT table_name FROM gpkg_contents WHERE data_type='features'")]
        except sqlite3.Error:
            return None

        def is_tracage(t):
            cols = {r[1] for r in cur.execute(f'PRAGMA table_info("{t}")')}
            return bool(markers & cols)

        for cand in (preferred, "tracages"):
            if cand in tables and is_tracage(cand):
                return cand
        for t in tables:
            if is_tracage(t):
                return t
    return None
