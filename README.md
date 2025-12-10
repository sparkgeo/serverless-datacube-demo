# Serverless Data Cube Demo

## Hook Interface

Filtering and masking logic is now pluggable via hooks in `src/hooks.py`:

Default implementations:

- `DefaultCloudMaskHook`: no-op; passes bands through without masking.
- `SCLCloudMaskHook`: applies Sentinel-2 SCL-based masking with cleanup.

`JobConfig` accepts an optional `cloud_mask_hook` selected via CLI.

- Cloud mask: `--cloud-mask none` (default) applies no masking; `--cloud-mask scl` enables SCL-based masking.
  When `--geometry-file` is provided, it defines the spatial bounds used for tiling and search; geometry is not used as a land filter.

### Example

```python
from src.hooks import SCLCloudMaskHook

cfg = JobConfig(
  dx=0.0005,
  epsg=4326,
  bounds=(minx, miny, maxx, maxy),
  start_date=start,
  end_date=end,
  time_frequency_months=1,
  bands=["red","green","blue","nir"],
  varname="rgb_median",
  chunk_size=600,
  cloud_mask_hook=SCLCloudMaskHook(),
)
```

To customize behavior, implement your own hooks by conforming to the `Protocol` signatures in `src/hooks.py`.

 
## Project Overview

This repo demonstrates how to build a Zarr-based data cube from [Sentinel 2 L2A Data](https://registry.opendata.aws/sentinel-2-l2a-cogs/)
in the AWS Open Data Program.

License: Apache 2.0

### Supported Serverless Backends

- Local (Dask threads)
- Coiled Functions

### Supported Storage Locations

- Any [fsspec](https://filesystem-spec.readthedocs.io/en/latest/)-compatible cloud storage location (e.g. S3)

## CLI Reference

```zsh
% python src/main.py --help
Usage: main.py [OPTIONS]

Options:
  --start-date [%Y-%m-%d|%Y-%m-%dT%H:%M:%S|%Y-%m-%d %H:%M:%S]
                                  Start date for the data cube. Everything but
                                  year and month will be ignored.  [required]
  --end-date [%Y-%m-%d|%Y-%m-%dT%H:%M:%S|%Y-%m-%d %H:%M:%S]
                                  Start date for the data cube. Everything but
                                  year and month will be ignored.  [required]
  --bbox <FLOAT FLOAT FLOAT FLOAT>...
                                  Bounding box for the data cube in lat/lon.
                                  (min_lon, min_lat, max_lon, max_lat). Use
                                  this OR --geometry-file, not both.
  --geometry-file PATH            Path to a shapefile or GeoPackage containing
                                  geometries to process. Supported formats:
                                  .shp, .gpkg
  --time-frequency-months INTEGER RANGE
                                  Temporal sampling frequency in months.
                                  [1<=x<=24]
  --resolution FLOAT              Spatial resolution in degrees.  [default:
                                  0.0002777777777777778]
  --chunk-size INTEGER            Zarr chunk size for the data cube.
                                  [default: 1200]
  --bands TEXT                    Bands to include in the data cube. Must
                                  match band names from odc.stac.load
                                  [default: red, green, blue, nir]
  --varname TEXT                  The name of the variable to use in the Zarr
                                  data cube.  [default: rgb_median]
  --epsg [4326]                   EPSG for the data cube. Only 4326 is
                                  supported at the moment.  [default: 4326]
  --serverless-backend [coiled|local]
                                  [required]
  --storage-backend [fsspec]      [default: fsspec; required]
  --fsspec-uri TEXT
  --limit INTEGER                 Limit the number of chunks to process.
  --debug                         Enable debug logging.
  --initialize / --no-initialize  Initialize the Zarr store before processing.
  --cloud-mask [none|scl]         Cloud masking: 'none' (pass-through) or
                                  'scl' (Sentinel-2 SCL-based mask).
                                  [default: none]
  --help                          Show this message and exit.
```

## Quick Start

Local run with SCL cloud mask:

```zsh
python src/main.py \
  --bbox -123.3 48.9 -122.9 49.4 \
  --start-date 2023-01-01 \
  --end-date 2023-03-31 \
  --cloud-mask scl \
  --storage-backend fsspec \
  --serverless-backend local \
  --fsspec-uri ./output/vancouer-test
```

## Docker

Build the image and run the CLI inside the container. The image entrypoint runs `python /app/src/main.py`, so you only need to pass flags.

### Build

```zsh
./scripts/build
```

### Run with mounts (recommended)

```zsh
./scripts/start \
  --initialize \
  --geometry-file /app/data/ok-test.gpkg \
  --start-date 2023-01-01 \
  --end-date 2025-12-31 \
  --storage-backend fsspec \
  --serverless-backend local \
  --fsspec-uri /app/output/ok-test
```

This mounts your local `src`, `data`, and `output` into the container at `/app/src`, `/app/data`, and `/app/output` and forwards any CLI flags.

### Credentials

- Explicit envs via `.creds.env`:
  1. Export AWS variables in your shell (e.g., `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_DEFAULT_REGION`).
  2. Generate env file:

     ```zsh
     ./scripts/creds
     ```

  3. `./scripts/start` automatically uses `--env-file .creds.env`.

- Alternatively, pass envs directly to `docker run` if not using the scripts.

## Scripts to Rule Them All

Common entry points for development and runs:

- `./scripts/setup`: prepare local environment (optional)
- `./scripts/build`: builds the Docker image (`ard-process:latest`)
- `./scripts/start`: runs the Dockerized CLI with standard mounts and flags
- `./scripts/creds`: writes `.creds.env` from your current shell envs for simple credential injection

These scripts keep build/run consistent and minimal. Use `./scripts/start --help` to see CLI flags.

### Local Dask backend

Run locally using the `local` backend. You can also pass a geometry file (SHP/GPKG); geometry defines bounds only.

```zsh
python src/main.py \
  --geometry-file data/ok-test.gpkg \
  --start-date 2023-01-01 \
  --end-date 2025-12-31 \
  --storage-backend fsspec \
  --serverless-backend local \
  --fsspec-uri ./output/ok-test
```

Notes:

- `--geometry-file` accepts `.shp` or `.gpkg`; geometries are reprojected to EPSG:4326 if needed.
  
- `--fsspec-uri` supports local paths (e.g., `./output/ok-test` or `file:///...`) and cloud URIs depending on your fsspec drivers.
- Zarr v3 is used; ensure your environment supports it. If required, set:
  
  ```zsh
  export ZARR_V3_EXPERIMENTAL_API=1
  ```

### Coiled backend

Run on Coiled:

```zsh
python src/main.py \
  --bbox -123.3 48.9 -122.9 49.4 \
  --start-date 2023-01-01 \
  --end-date 2023-12-31 \
  --storage-backend fsspec \
  --serverless-backend coiled \
  --fsspec-uri s3://your-bucket/path
```

### Geometry vs BBox

Provide either `--bbox` or `--geometry-file` (not both). With `--geometry-file`, the overall bounds are computed from the geometries; optionally filter tiles that intersect the geometries using `--use-geometry-mask`.
