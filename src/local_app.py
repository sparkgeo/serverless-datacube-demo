from __future__ import annotations

from typing import Iterable, List, Optional

import zarr
from dask.distributed import Client, LocalCluster, as_completed
from tqdm import tqdm

from lib import ChunkProcessingJob, ChunkProcessingResult


def _process_chunk_local(
    job: ChunkProcessingJob, array: zarr.Array, debug: bool
) -> Optional[ChunkProcessingResult]:
    return job.process(array, debug=debug)


def _run_with_retry(
    job: ChunkProcessingJob, array: zarr.Array, debug: bool, max_retries: int = 5
) -> Optional[ChunkProcessingResult]:
    attempt = 0
    while True:
        try:
            return _process_chunk_local(job, array, debug)
        except Exception:
            attempt += 1
            if attempt >= max_retries:
                # Let the job record failure inside process or return None
                return None
            # simple retry without backoff to match Coiled semantics


def spawn_local_jobs(
    jobs: Iterable[ChunkProcessingJob], array: zarr.Array, debug: bool
) -> List[Optional[ChunkProcessingResult]]:
    # Use threaded workers to avoid cross-process serialization of zarr.Array
    cluster = LocalCluster(processes=False)
    client = Client(cluster)
    try:
        futures = [
            client.submit(_run_with_retry, job, array, debug, max_retries=5)
            for job in jobs
        ]

        results: List[Optional[ChunkProcessingResult]] = []
        for fut in tqdm(as_completed(futures), total=len(futures), desc="Jobs Completed"):
            results.append(fut.result())
        return results
    finally:
        client.close()
        cluster.close()
