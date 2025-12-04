# src/grid.py

from dataclasses import dataclass
from typing import Optional, Tuple, Callable, Union, Iterable, Dict, Any

import geopandas as gpd
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from affine import Affine
from math import floor, ceil

from odc.geo.geobox import GeoBox
from odc.geo import CRS

# Optional MajorTom
try:
    from majortom_eg.MajorTom import MajorTomGrid
    _HAS_MAJORTOM = True
except Exception:
    _HAS_MAJORTOM = False


@dataclass
class GridSpec:
    d: int = 512
    overlap: bool = True
    target_crs: Union[str, CRS] = "EPSG:32610"
    res_m: int = 16
    id_column: str = "grid_id"


def _ensure_crs_string(crs: Union[str, CRS]) -> str:
    if isinstance(crs, CRS):
        epsg = crs.to_epsg()
        return str(epsg) if epsg else str(crs)
    return str(crs)


# -----------------------
# AOI format-only loader
# -----------------------

def load_geometry_file(
    geometry_path: str,
    layer: Optional[str] = None,
) -> BaseGeometry:
    """
    Format-agnostic geometry loader:
    - Auto-detects file type: GeoPackage, Shapefile, GeoJSON, etc.
    - Reads the first/specified layer.
    - Dissolves to a single geometry via unary_union.
    - Returns geometry in EPSG:4326 (lon/lat).
    - Does NOT modify topology, holes, or validity (format-only).
    
    Supported formats (via geopandas.read_file):
    - GeoPackage (.gpkg)
    - Shapefile (.shp)
    - GeoJSON (.geojson, .json)
    - GML (.gml)
    - KML (.kml)
    - And any format supported by fiona
    
    Args:
        geometry_path: Path to geometry file.
        layer: Optional layer name (for formats supporting multiple layers).
    
    Returns:
        Single Shapely BaseGeometry in EPSG:4326.
    
    Raises:
        ValueError: If file is empty, geometry is invalid, or file cannot be read.
    """
    try:
        gdf = gpd.read_file(geometry_path, layer=layer) if layer else gpd.read_file(geometry_path)
    except Exception as e:
        raise ValueError(f"Failed to read geometry file '{geometry_path}': {e}")
    
    if gdf.empty:
        raise ValueError(f"No features found in geometry file: {geometry_path}")
    
    geom = unary_union([g for g in gdf.geometry if g and not g.is_empty])
    if geom.is_empty:
        raise ValueError("Geometry is empty after union. Check input file for valid geometries.")
    
    # Ensure CRS is set (default to EPSG:4326 if missing)
    source_crs = gdf.crs or "EPSG:4326"
    aoi_4326 = gpd.GeoSeries([geom], crs=source_crs).to_crs("EPSG:4326").iloc[0]
    return aoi_4326


def load_aoi_lonlat_from_gpkg(
    gpkg_path: str,
    layer: Optional[str] = None,
) -> BaseGeometry:
    """
    Deprecated: Use load_geometry_file() instead.
    
    Format-only loader for GeoPackage files.
    """
    return load_geometry_file(gpkg_path, layer=layer)


# -----------------------
# Generators (pluggable)
# -----------------------

def majortom_generator(d: int = 512, overlap: bool = True) -> Callable[[BaseGeometry], gpd.GeoDataFrame]:
    """
    MajorTom grid generator from UESA.
    
    Args:
        d: Grid dimension parameter (controls cell size/granularity).
        overlap: If True, generates overlapping cells for better coverage.
    
    Returns:
        A generator function that takes an AOI geometry and returns GeoDataFrame of grid cells.
    """
    if not _HAS_MAJORTOM:
        raise ImportError("majortom_eg not available. Install `majortom_eg` to use this generator.")
    def _gen(aoi_4326: BaseGeometry) -> gpd.GeoDataFrame:
        mt = MajorTomGrid(d=d, overlap=overlap)
        cells = mt.generate_grid_cells(aoi_4326)
        rows = [{"grid_id": cell.id(), "geometry": cell.geom} for cell in cells]
        gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
        if gdf.empty:
            raise ValueError("MajorTom generated 0 cells; check AOI extent and parameters.")
        return gdf
    return _gen


def square_tiling_generator(cell_size_m: int = 512, work_crs: Union[str, CRS] = "EPSG:32610") -> Callable[[BaseGeometry], gpd.GeoDataFrame]:
    """
    Tiles AOI bounding box with fixed-size squares in a projected CRS,
    clips to AOI, and returns EPSG:4326. Format-only: no shape changes to AOI.
    """
    def _gen(aoi_4326: BaseGeometry) -> gpd.GeoDataFrame:
        crs_str = _ensure_crs_string(work_crs)
        aoi_proj = gpd.GeoSeries([aoi_4326], crs="EPSG:4326").to_crs(crs_str)[0]
        minx, miny, maxx, maxy = aoi_proj.bounds

        minx = floor(minx / cell_size_m) * cell_size_m
        miny = floor(miny / cell_size_m) * cell_size_m
        maxx = ceil(maxx / cell_size_m) * cell_size_m
        maxy = ceil(maxy / cell_size_m) * cell_size_m

        rows = []
        gid = 0
        y = miny
        while y < maxy:
            x = minx
            while x < maxx:
                poly = Polygon([(x, y), (x + cell_size_m, y), (x + cell_size_m, y + cell_size_m), (x, y + cell_size_m)])
                rows.append({"grid_id": f"square_{gid}", "geometry": poly})
                gid += 1
                x += cell_size_m
            y += cell_size_m

        gdf_proj = gpd.GeoDataFrame(rows, crs=crs_str)
        gdf_proj = gpd.overlay(gdf_proj, gpd.GeoDataFrame(geometry=[aoi_proj], crs=crs_str), how="intersection")
        return gdf_proj.to_crs("EPSG:4326")
    return _gen


def custom_generator(func: Callable[[BaseGeometry], Union[gpd.GeoDataFrame, Iterable[Dict[str, Any]]]]) -> Callable[[BaseGeometry], gpd.GeoDataFrame]:
    """
    Wrap any external tiling/grid function. Must return polygons in EPSG:4326.

    DGGS pseudocode example:
      def dggs_generator(resolution: int):
          def _gen(aoi_4326):
              # cells = DGGS.cover_polygon(aoi_4326, resolution=resolution)
              # rows = [{"grid_id": c.id, "geometry": c.boundary_polygon} for c in cells]
              # return geopandas.GeoDataFrame(rows, crs="EPSG:4326")
              pass
          return _gen
    """
    def _gen(aoi_4326: BaseGeometry) -> gpd.GeoDataFrame:
        out = func(aoi_4326)
        if isinstance(out, gpd.GeoDataFrame):
            if out.crs is None or str(out.crs).lower() not in ("epsg:4326", "4326"):
                out = out.set_crs("EPSG:4326", allow_override=True)
            return out
        rows = list(out)
        gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
        if "geometry" not in gdf.columns:
            raise ValueError("Custom generator must supply 'geometry' polygons.")
        if "grid_id" not in gdf.columns:
            gdf["grid_id"] = [f"cell_{i}" for i in range(len(gdf))]
        return gdf
    return _gen


# -----------------------
# Reprojection + Mosaic
# -----------------------

def reproject_cells(cells_4326: gpd.GeoDataFrame, target_crs: Union[str, CRS]) -> gpd.GeoDataFrame:
    return cells_4326.to_crs(_ensure_crs_string(target_crs))


def build_mosaic_geobox(cells_in_target_crs: gpd.GeoDataFrame, target_crs: Union[str, CRS], res_m: int) -> GeoBox:
    crs_str = _ensure_crs_string(target_crs)
    minx, miny, maxx, maxy = cells_in_target_crs.total_bounds
    xmin = floor(minx / res_m) * res_m
    ymax = ceil(maxy / res_m) * res_m
    xmax = ceil(maxx / res_m) * res_m
    ymin = floor(miny / res_m) * res_m

    nx = int(round((xmax - xmin) / res_m))
    ny = int(round((ymax - ymin) / res_m))

    A = Affine.translation(xmin, ymax) * Affine.scale(res_m, -res_m)
    return GeoBox((ny, nx), A, CRS(crs_str))


# -----------------------
# High-level API
# -----------------------

def load_grid_for_aoi(
    geometry_path: str,
    spec: Optional[GridSpec] = None,
    layer: Optional[str] = None,
    generator: Optional[Callable[[BaseGeometry], gpd.GeoDataFrame]] = None,
) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, GeoBox]:
    """
    Format-agnostic grid generation workflow:
    - Read AOI from any supported file format (GPKG, Shapefile, GeoJSON, etc.).
    - Union to single geometry, convert to EPSG:4326 (no topology changes).
    - Generate grid cells via `generator` (defaults to MajorTom if installed, else square tiler).
    - Reproject cells to `spec.target_crs`.
    - Build mosaic `GeoBox` aligned to `spec.res_m`.
    
    Args:
        geometry_path: Path to geometry file (auto-detected format).
        spec: GridSpec with d, overlap, target_crs, res_m (optional, uses defaults).
        layer: Layer name for formats supporting multiple layers.
        generator: Custom grid generator function; defaults to majortom or square tiler.
    
    Returns:
        Tuple of (cells_4326, cells_target, gbox_mosaic):
        - cells_4326: GeoDataFrame with grid cells in EPSG:4326.
        - cells_target: GeoDataFrame with grid cells in spec.target_crs.
        - gbox_mosaic: GeoBox aligned to res_m for odc.stac integration.
    """
    spec = spec or GridSpec()
    aoi_4326 = load_geometry_file(geometry_path, layer=layer)

    if generator is None:
        generator = majortom_generator(d=spec.d, overlap=spec.overlap) if _HAS_MAJORTOM else square_tiling_generator(cell_size_m=spec.d, work_crs=spec.target_crs)

    cells_4326 = generator(aoi_4326)
    if cells_4326.empty:
        raise ValueError("Grid generator produced no cells for AOI.")

    cells_target = reproject_cells(cells_4326, spec.target_crs)
    gbox_mosaic = build_mosaic_geobox(cells_target, spec.target_crs, spec.res_m)
    return cells_4326, cells_target, gbox_mosaic