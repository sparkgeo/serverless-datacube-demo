from datetime import datetime
from pathlib import Path

import click
import geopandas as gpd
import zarr
from coiled_app import spawn_coiled_jobs
from lib import JobConfig, save_output_log, load_geometries
from hooks import (
    DefaultCloudMaskHook,
    SCLCloudMaskHook,
)
from storage import ZarrFSSpecStorage


@click.command()
@click.option(
    "--start-date",
    type=click.DateTime(),
    required=True,
    help="Start date for the data cube. Everything but year and month will be ignored.",
)
@click.option(
    "--end-date",
    type=click.DateTime(),
    required=True,
    help="Start date for the data cube. Everything but year and month will be ignored.",
)
@click.option(
    "--bbox",
    type=click.Tuple([float, float, float, float]),
    help="Bounding box for the data cube in lat/lon. "
    "(min_lon, min_lat, max_lon, max_lat). Use this OR --geometry-file, not both.",
)
@click.option(
    "--geometry-file",
    type=click.Path(exists=True),
    help="Path to a shapefile or GeoPackage containing geometries to process. "
    "Supported formats: .shp, .gpkg",
)
@click.option(
    "--time-frequency-months",
    default=1,
    type=click.IntRange(1, 24),
    help="Temporal sampling frequency in months.",
)
@click.option(
    "--resolution",
    type=float,
    default=1 / 3600,
    show_default=True,
    help="Spatial resolution in degrees.",
)
@click.option(
    "--chunk-size",
    type=int,
    default=1200,
    show_default=True,
    help="Zarr chunk size for the data cube.",
)
@click.option(
    "--bands",
    multiple=True,
    default=["red", "green", "blue", "nir"],
    show_default=True,
    help="Bands to include in the data cube. Must match band names from odc.stac.load",
)
@click.option(
    "--varname",
    default="rgb_median",
    show_default=True,
    help="The name of the variable to use in the Zarr data cube.",
)
@click.option(
    "--epsg",
    type=click.Choice(["4326"]),
    default="4326",
    show_default=True,
    help="EPSG for the data cube. Only 4326 is supported at the moment.",
)
@click.option(
    "--serverless-backend",
    required=True,
    default="coiled",
    type=click.Choice(["coiled", "local"]),
)
@click.option(
    "--storage-backend",
    required=True,
    type=click.Choice(["fsspec"]),
    default="fsspec",
    show_default=True,
)
@click.option("--fsspec-uri")
@click.option(
    "--limit",
    type=int,
    help="Limit the number of chunks to process.",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Enable debug logging.",
)
@click.option(
    "--initialize/--no-initialize",
    is_flag=True,
    default=True,
    help="Initialize the Zarr store before processing.",
)
@click.option(
    "--cloud-mask",
    type=click.Choice(["none", "scl"]),
    default="none",
    show_default=True,
    help="Cloud masking: 'none' (pass-through) or 'scl' (Sentinel-2 SCL-based mask).",
)
def main(
    start_date: datetime,
    end_date: datetime,
    bbox: tuple[float, float, float, float] | None,
    geometry_file: str | None,
    time_frequency_months: int,
    resolution: float,
    chunk_size: int,
    bands: list[str],
    varname: str,
    epsg: str,
    serverless_backend: str,
    storage_backend: str,
    fsspec_uri: str | None,
    limit: int | None,
    initialize: bool,
    debug: bool,
    cloud_mask: str,
):
    # Validate that user provided either bbox or geometry_file, but not both
    if bbox is None and geometry_file is None:
        raise click.UsageError("Either --bbox or --geometry-file must be provided.")
    if bbox is not None and geometry_file is not None:
        raise click.UsageError("Cannot use both --bbox and --geometry-file. Choose one.")

    # Load geometries if geometry file is provided
    geometries = None
    if geometry_file:
        geometries = load_geometries(geometry_file)
        # Extract bounds from geometries to define the overall spatial extent
        bounds = tuple(geometries.total_bounds)  # (minx, miny, maxx, maxy)
    else:
        bounds = bbox

    # Select cloud mask hook from CLI
    cloud_mask_mapping = {
        "none": DefaultCloudMaskHook(),
        "scl": SCLCloudMaskHook(),
    }
    cloud_hook = cloud_mask_mapping[cloud_mask]

    job_config = JobConfig(
        dx=resolution,
        epsg=int(epsg),
        bounds=bounds,
        start_date=start_date,
        end_date=end_date,
        time_frequency_months=time_frequency_months,
        bands=bands,
        varname=varname,
        chunk_size=chunk_size,
        geometries=geometries,
        cloud_mask_hook=cloud_hook,
    )

    storage = ZarrFSSpecStorage(uri=fsspec_uri)

    if initialize:
        job_config.create_dataset_schema(storage)

    with click.progressbar(
        job_config.generate_jobs(limit=(limit or 0)),
        label=f"Computing {job_config.num_tiles} tile intersections",
        length=job_config.num_jobs,
    ) as job_gen:
        jobs = list(job_gen)

    if serverless_backend == "coiled":
        spawn = spawn_coiled_jobs
    elif serverless_backend == "local":
        from local_app import spawn_local_jobs
        spawn = spawn_local_jobs
    else:
        raise NotImplementedError

    with storage.get_zarr_store() as store:
        target_array = zarr.open_array(
            store, path=job_config.varname, zarr_format=3, mode="a"
        )

        with click.progressbar(
            jobs,
            label=f"Spawning {len(jobs)} jobs",
            length=len(jobs),
        ) as jobs_progress:
            # all the work happens here
            results = spawn(jobs_progress, target_array, debug=debug)

    # commit changes only of successful
    storage.commit(f"Processed {len(jobs)} chunks", results=results)

    # save logs
    log_fname = f"./logs/{int(datetime.now().timestamp())}-{serverless_backend}.csv"
    save_output_log(results, log_fname)


if __name__ == "__main__":
    main()