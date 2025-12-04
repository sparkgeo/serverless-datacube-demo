# Serverless Sentinel Mosaic

This repo demonstrates how to build a Zarr-based data cube from [Sentinel 2 L2A Data](https://registry.opendata.aws/sentinel-2-l2a-cogs/)
in the AWS Open Data Program using serverless compute and pluggable grid generation strategies.

**License:** Apache 2.0

**Supported Serverless Backends**

- [Coiled Functions](https://docs.coiled.io/user_guide/usage/functions/index.html)

**Supported Storage Locations**

- Any [fsspec](https://filesystem-spec.readthedocs.io/en/latest/)-compatible cloud storage location (e.g. S3)

**Grid Generation**

- **MajorTom**: ESA grid generator with configurable cell sizes and overlap
- **Square Tiling**: Regular grid squares in any projected CRS
- **Custom**: Pluggable generator interface for external grid schemes (DGGS, etc.)

## Features

### Multi-Format Geometry Support
Load AOI geometries from multiple file formats:
- GeoPackage (`.gpkg`) with multi-layer support
- Shapefile (`.shp`)
- GeoJSON (`.geojson`, `.json`)
- GML, KML, and any [fiona](https://fiona.readthedocs.io/)-supported format

### Pluggable Grid Generation
Choose grid generation strategy at runtime:
```python
from grid import load_grid_for_aoi, GridSpec, majortom_generator, square_tiling_generator

# Generate grid with MajorTom
cells_4326, cells_target, mosaic = load_grid_for_aoi(
    "data/aoi.geojson",
    spec=GridSpec(d=512, overlap=True, target_crs="EPSG:32610", res_m=16),
    generator=majortom_generator(d=512, overlap=True)
)

# Or with square tiling
cells_4326, cells_target, mosaic = load_grid_for_aoi(
    "data/aoi.shp",
    spec=GridSpec(d=512, target_crs="EPSG:32610", res_m=16),
    generator=square_tiling_generator(cell_size_m=512, work_crs="EPSG:32610")
)
```

## Usage

```
% python src/main.py --help
Usage: main.py [OPTIONS]

Options:
  --geometry-file PATH            Geometry file (GPKG, Shapefile, GeoJSON, etc.)
                                  to use as AOI. Alternative to --bbox.
  --geometry-layer TEXT           Layer name for multi-layer geometry formats.
  --bbox <FLOAT FLOAT FLOAT FLOAT>
                                  Bounding box in lat/lon (min_lon, min_lat,
                                  max_lon, max_lat). Required if
                                  --geometry-file not provided.
  --grid-generator [majortom|square]
                                  Grid generation strategy (requires
                                  --geometry-file). 'majortom' uses MajorTom
                                  cells; 'square' uses regular grid squares.
                                  [default: majortom]
  --grid-d INTEGER                Grid dimension (MajorTom: size; square: cell
                                  size in meters). Only used with
                                  --geometry-file.  [default: 512]
  --grid-overlap / --no-grid-overlap
                                  Enable overlapping cells (MajorTom only).
                                  Only used with --geometry-file.  [default:
                                  True]
  --grid-crs TEXT                 Target CRS for grid cells. Only used with
                                  --geometry-file.  [default: EPSG:32610]
  --grid-res INTEGER              Mosaic resolution in meters for GeoBox
                                  alignment. Only used with --geometry-file.
                                  [default: 16]
  --start-date [%Y-%m-%d|...]     Start date for the data cube. Everything but
                                  year and month will be ignored.  [required]
  --end-date [%Y-%m-%d|...]       End date for the data cube. Everything but
                                  year and month will be ignored.  [required]
  --time-frequency-months INTEGER Temporal sampling frequency in months.
                                  [1<=x<=24; default: 1]
  --resolution FLOAT              Spatial resolution in degrees.  [default:
                                  0.0002777...]
  --chunk-size INTEGER            Zarr chunk size for the data cube.
                                  [default: 1200]
  --bands TEXT                    Bands to include in the data cube.
                                  [default: red, green, blue]
  --varname TEXT                  Variable name in Zarr data cube.
                                  [default: rgb_median]
  --epsg [4326]                   EPSG code. Only 4326 supported.  [default: 4326]
  --serverless-backend [coiled]   Serverless compute backend.  [required]
  --storage-backend [fsspec]      Storage backend.  [default: fsspec; required]
  --fsspec-uri TEXT               S3/cloud storage URI
  --limit INTEGER                 Limit chunks to process (for testing)
  --debug                         Enable debug logging
  --initialize / --no-initialize  Initialize Zarr store before processing.
                                  [default: True]
  --help                          Show this message and exit.
```

## Example Usage

### Using Bounding Box (Original Workflow)
```bash
python src/main.py \
  --start-date 2020-01-01 \
  --end-date 2023-12-31 \
  --bbox -73.43 42.72 -71.47 45.02 \
  --storage-backend fsspec \
  --serverless-backend coiled \
  --fsspec-uri s3://my-bucket/zarr/vermont
```

### Using Geometry File with MajorTom Grid (Recommended)
```bash
python src/main.py \
  --geometry-file data/vancouver-test.gpkg \
  --grid-generator majortom \
  --grid-d 512 \
  --grid-overlap \
  --start-date 2020-01-01 \
  --end-date 2023-12-31 \
  --storage-backend fsspec \
  --serverless-backend coiled \
  --fsspec-uri s3://my-bucket/zarr/vancouver
```

### Using Geometry File with Square Tiling
```bash
python src/main.py \
  --geometry-file data/vancouver-test.gpkg \
  --grid-generator square \
  --grid-d 1024 \
  --grid-crs EPSG:32610 \
  --grid-res 32 \
  --start-date 2020-01-01 \
  --end-date 2023-12-31 \
  --storage-backend fsspec \
  --serverless-backend coiled \
  --fsspec-uri s3://my-bucket/zarr/vancouver
```

### Using GeoPackage with Specific Layer
```bash
python src/main.py \
  --geometry-file data/vancouver-test.gpkg \
  --geometry-layer my_layer \
  --grid-generator majortom \
  --start-date 2020-01-01 \
  --end-date 2023-12-31 \
  --storage-backend fsspec \
  --serverless-backend coiled \
  --fsspec-uri s3://my-bucket/zarr/vancouver
```

## Grid Module API

The `src/grid.py` module provides a pluggable grid generation interface for any AOI.

### Core Functions

#### `load_geometry_file(geometry_path, layer=None) → BaseGeometry`
Auto-detects file format and loads geometry.
- Supports: GeoPackage, Shapefile, GeoJSON, GML, KML, etc.
- Returns: Single unioned geometry in EPSG:4326
- Format-only: No topology normalization or modification

```python
from grid import load_geometry_file

aoi = load_geometry_file("data/aoi.geojson")
aoi = load_geometry_file("data/aoi.gpkg", layer="my_layer")
```

#### `load_grid_for_aoi(geometry_path, spec=None, layer=None, generator=None) → (cells_4326, cells_target, gbox_mosaic)`
Generate grid cells from AOI geometry.
- Returns: Grid cells in EPSG:4326, cells in target CRS, and aligned mosaic GeoBox
- Format-only geometry handling (no normalization)
- Default generator: MajorTom (if available) or square tiling

```python
from grid import load_grid_for_aoi, GridSpec, square_tiling_generator

spec = GridSpec(d=512, target_crs="EPSG:32610", res_m=16)
cells_4326, cells_target, gbox = load_grid_for_aoi(
    "data/aoi.geojson",
    spec=spec,
    generator=square_tiling_generator(cell_size_m=512)
)
```

### GridSpec Configuration

```python
from grid import GridSpec

spec = GridSpec(
    d=512,                      # Grid dimension/cell size
    overlap=True,               # Enable overlapping cells (MajorTom)
    target_crs="EPSG:32610",   # Target CRS for grid cells
    res_m=16,                   # Mosaic resolution in meters
    id_column="grid_id"         # Column name for cell IDs
)
```

### Grid Generators

#### MajorTom Generator
```python
from grid import majortom_generator

gen = majortom_generator(d=512, overlap=True)
cells = gen(aoi_geometry)
```

#### Square Tiling Generator
```python
from grid import square_tiling_generator

gen = square_tiling_generator(cell_size_m=512, work_crs="EPSG:32610")
cells = gen(aoi_geometry)
```

#### Custom Generator
```python
from grid import custom_generator

def my_tiling_func(aoi_geom):
    # Your grid generation logic here
    # Return GeoDataFrame with 'geometry' and 'grid_id' columns
    return geopandas.GeoDataFrame([...], crs="EPSG:4326")

gen = custom_generator(my_tiling_func)
cells = gen(aoi_geometry)
```

## Installation

```bash
pip install -r requirements.txt
```

Optional: Install MajorTom grid generator
```bash
pip install majortom_eg
```

## Architecture

- **src/grid.py**: Pluggable grid generation with multi-format geometry support
- **src/lib.py**: Core data processing and job configuration
- **src/main.py**: CLI with geometry file and grid generator options
- **src/coiled_app.py**: Serverless job orchestration
- **src/storage.py**: Storage abstraction (Zarr, Icechunk, etc.)
