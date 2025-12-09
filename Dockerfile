FROM python:3.12-slim

# System dependencies (minimal): PROJ/GEOS for cartopy/rasterio may be needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ \
    make \
    libproj-dev \
    proj-bin \
    libgeos-dev \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ZARR_V3_EXPERIMENTAL_API=1

WORKDIR /app

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application sources
COPY src /app/src
COPY data /app/data

# Run the CLI directly via Python
ENTRYPOINT ["python", "/app/src/main.py"]
CMD ["--help"]
