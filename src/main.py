from datetime import datetime

import click
import zarr
from coiled_app import spawn_coiled_jobs
from lib import JobConfig, save_output_log
from storage import ZarrFSSpecStorage
from grid import load_geometry_file, load_grid_for_aoi, GridSpec, majortom_generator, square_tiling_generator


@click.command()
@click.option(
    "--geometry-file",
    type=click.Path(exists=True),
    default=None,
    help="Geometry file (GPKG, Shapefile, GeoJSON, etc.) to use as AOI. Alternative to --bbox.",
)
@click.option(
    "--geometry-layer",
    default=None,
    help="Layer name for multi-layer geometry formats (GeoPackage, Shapefile).",
)
@click.option(
    "--bbox",
    type=click.Tuple([float, float, float, float]),
    default=None,
    help="Bounding box in lat/lon (min_lon, min_lat, max_lon, max_lat). Required if --geometry-file not provided.",
)
@click.option(
    "--grid-generator",
    type=click.Choice(["majortom", "square"]),
    default="majortom",
    show_default=True,
    help="Grid generation strategy (requires --geometry-file). 'majortom' uses MajorTom cells; 'square' uses regular grid squares.",
)
@click.option(
    "--grid-d",
    type=int,
    default=512,
    show_default=True,
    help="Grid dimension (MajorTom:  size; square: cell size in meters). Only used with --geometry-file.",
)
@click.option(
    "--grid-overlap/--no-grid-overlap",
    default=True,
    show_default=True,
    help="Enable overlapping cells (MajorTom only). Only used with --geometry-file.",
)
@click.option(
    "--grid-crs",
    default="EPSG:32610",
    show_default=True,
    help="Target CRS for grid cells. Only used with --geometry-file.",
)
@click.option(
    "--grid-res",
    type=int,
    default=16,
    show_default=True,
    help="Mosaic resolution in meters for GeoBox alignment. Only used with --geometry-file.",
)
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
    default=["red", "green", "blue"],
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
    type=click.Choice(["coiled"]),
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
def main(
    geometry_file: str | None,
    geometry_layer: str | None,
    bbox: tuple[float, float, float, float] | None,
    grid_generator: str,
    grid_d: int,
    grid_overlap: bool,
    grid_crs: str,
    grid_res: int,
    start_date: datetime,
    end_date: datetime,
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
):
    # Validate AOI input
    if not geometry_file and not bbox:
        raise click.UsageError("Must provide either --geometry-file or --bbox")
    
    if geometry_file and bbox:
        raise click.UsageError("Provide only one of --geometry-file or --bbox, not both")
    
    # Determine bounds
    if geometry_file:
        try:
            # Create grid from geometry file
            grid_spec = GridSpec(
                d=grid_d,
                overlap=grid_overlap,
                target_crs=grid_crs,
                res_m=grid_res,
            )
            
            # Create generator based on user choice
            if grid_generator == "majortom":
                generator = majortom_generator(d=grid_d, overlap=grid_overlap)
            else:  # square
                generator = square_tiling_generator(cell_size_m=grid_d, work_crs=grid_crs)
            
            # Generate grid
            cells_4326, cells_target, gbox_mosaic = load_grid_for_aoi(
                geometry_file,
                spec=grid_spec,
                layer=geometry_layer,
                generator=generator,
            )
            
            bounds = tuple(cells_4326.total_bounds)
            click.echo(f"✓ Loaded geometry from {geometry_file}")
            click.echo(f"✓ Generated {len(cells_target)} grid cells using {grid_generator}")
        except Exception as e:
            click.echo(f"✗ Error: {e}", err=True)
            raise SystemExit(1)
    else:
        bounds = bbox
    
    job_config = JobConfig(
        dx=resolution,
        epsg=int(epsg),
        bounds=bounds,  # type: ignore
        start_date=start_date,
        end_date=end_date,
        time_frequency_months=time_frequency_months,
        bands=bands,
        varname=varname,
        chunk_size=chunk_size,
    )

    storage = ZarrFSSpecStorage(uri=fsspec_uri)

    if initialize:
        job_config.create_dataset_schema(storage)

    with click.progressbar(
        job_config.generate_jobs(limit=(limit or 0)),
        label=f"Computing {job_config.num_tiles} tile intersections with land mask",
        length=job_config.num_jobs,
    ) as job_gen:
        jobs = list(job_gen)

    if serverless_backend == "coiled":
        spawn = spawn_coiled_jobs
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
