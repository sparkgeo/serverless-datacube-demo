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
