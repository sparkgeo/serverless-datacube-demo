#!/bin/bash

python src/main.py \
    --start-date 2020-01-01 \
    --end-date 2025-12-31 \
    --bbox -73.43 42.72 -71.47 45.02 \
    --storage-backend fsspec \
    --serverless-backend coiled \
    --fsspec-uri s3://testing-embeddings-184161167200-ca-central-1/zarr_app/vermont