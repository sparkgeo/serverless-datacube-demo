# Serverless Sentinel Mosaic

This repo demonstrates how to build a Zarr-based data cube from [Sentinel 2 L2A Data](https://registry.opendata.aws/sentinel-2-l2a-cogs/)
in the AWS Open Data Program.

**License:** Apache 2.0

**Supported Serverless Backends**

- [Coiled Functions](https://docs.coiled.io/user_guide/usage/functions/index.html)

**Supported Storage Locations**

- Any [fsspec](https://filesystem-spec.readthedocs.io/en/latest/)-compatible cloud storage location (e.g. S3)

## Usage

```
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
                                  (min_lon, min_lat, max_lon, max_lat)
                                  [required]
  --time-frequency-months INTEGER RANGE
                                  Temporal sampling frequency in months.
                                  [1<=x<=24]
  --resolution FLOAT              Spatial resolution in degrees.  [default:
                                  0.0002777777777777778]
  --chunk-size INTEGER            Zarr chunk size for the data cube.
                                  [default: 1200]
  --bands TEXT                    Bands to include in the data cube. Must
                                  match band names from odc.stac.load
                                  [default: red, green, blue]
  --varname TEXT                  The name of the variable to use in the Zarr
                                  data cube.  [default: rgb_median]
  --epsg [4326]                   EPSG for the data cube. Only 4326 is
                                  supported at the moment.  [default: 4326]
  --serverless-backend [coiled]
                                  [required]
  --storage-backend [fsspec]
                                  [default: arraylake; required]
  --arraylake-repo-name TEXT
  --arraylake-bucket-nickname TEXT
  --fsspec-uri TEXT
  --limit INTEGER
  --debug
  --initialize / --no-initialize  Initialize the Zarr store before processing.
  --help                          Show this message and exit.
```

## Example Usage

Vermont, 4 years, store in S3 Zarr
```
python src/main.py --start-date 2020-01-01 --end-date 2023-12-31 --bbox -73.43 42.72 -71.47 45.02 --storage-backend fsspec --fsspec-uri s3://testing-embeddings-184161167200-ca-central-1/zarr_app/vermont2
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
  --skip-land-filter \
  --fsspec-uri /app/output/ok-test
```

This mounts your local `src`, `data`, and `output` into the container at `/app/src`, `/app/data`, and `/app/output` and forwards any CLI flags.

### Credentials

- Explicit envs via `.creds.env`:
  1. Export AWS/Coiled variables in your shell (e.g., `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_DEFAULT_REGION`, `COILED_TOKEN`, `COILED_API_TOKEN`, etc.)
  2. Generate env file:

     ```zsh
     ./scripts/creds
     ```

  3. `./scripts/start` automatically uses `--env-file .creds.env`

- Alternatively, pass envs directly to `docker run` if not using the scripts.

## Scripts to Rule Them All

Common entry points for development and runs:

- `./scripts/setup`: prepare local environment (optional)
- `./scripts/build`: builds the Docker image (`ard-process:latest`)
- `./scripts/start`: runs the Dockerized CLI with standard mounts and flags
- `./scripts/creds`: writes `.creds.env` from your current shell envs for simple credential injection

These scripts keep build/run consistent and minimal. Use `./scripts/start --help` to see CLI flags.

### Local Dask backend

Run locally without Coiled using the `local` backend. You can also pass a geometry file (SHP/GPKG) and disable Cartopy LAND filtering.

```zsh
python src/main.py \
  --geometry-file data/ok-test.gpkg \
  --start-date 2023-01-01 \
  --end-date 2025-12-31 \
  --storage-backend fsspec \
  --serverless-backend local \
  --skip-land-filter \
  --fsspec-uri ./output/ok-test
```

Notes:

- `--geometry-file` accepts `.shp` or `.gpkg`; geometries are reprojected to EPSG:4326 if needed.
- `--skip-land-filter` processes all tiles in the bounding box (no Cartopy LAND mask).
- `--fsspec-uri` supports local paths (e.g., `./output/ok-test` or `file:///...`) and cloud URIs depending on your fsspec drivers.
- Zarr v3 is used; ensure your environment supports it. If required, set:
  
  ```zsh
  export ZARR_V3_EXPERIMENTAL_API=1
  ```

### Coiled backend

Coiled remains the default serverless backend. Example:

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
