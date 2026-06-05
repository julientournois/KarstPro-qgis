# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
# Usage commercial interdit sans autorisation écrite — julien.tournois@gmail.com
# https://polyformproject.org/licenses/noncommercial/1.0.0
from dataclasses import dataclass
from pathlib import Path
import geopandas as gpd

_TARGET_CRS = "EPSG:2154"


@dataclass
class TopoNetwork:
    passages: gpd.GeoDataFrame  # linestrings in EPSG:2154


def load_topo(path: Path) -> TopoNetwork:
    """Loads a topo from .shp or .kml and reprojects to Lambert-93."""
    path = Path(path)
    if path.suffix.lower() == ".kml":
        gdf = gpd.read_file(path, driver="KML")
    else:
        gdf = gpd.read_file(path)

    from shapely.geometry import LineString

    lines = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()

    if lines.empty:
        # Polygons (e.g. KML export from Visual Topo) → exterior ring as LineString
        polys = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
        if not polys.empty:
            extracted = []
            for geom in polys.geometry:
                if geom.geom_type == "Polygon":
                    extracted.append(LineString(geom.exterior.coords))
                else:  # MultiPolygon
                    for part in geom.geoms:
                        extracted.append(LineString(part.exterior.coords))
            lines = gpd.GeoDataFrame(geometry=extracted, crs=gdf.crs)

    if lines.empty:
        # Last resort: connect Point geometries in order (survey stations)
        points = gdf[gdf.geometry.geom_type == "Point"].copy()
        if len(points) >= 2:
            line = LineString([(p.x, p.y) for p in points.geometry])
            lines = gpd.GeoDataFrame(geometry=[line], crs=gdf.crs)

    if lines.crs is None:
        lines = lines.set_crs("EPSG:32631")

    if str(lines.crs) != _TARGET_CRS:
        lines = lines.to_crs(_TARGET_CRS)

    return TopoNetwork(passages=lines.reset_index(drop=True))
