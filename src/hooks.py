"""
Hook interfaces for pluggable masking logic.

- CloudMaskHook: applies cloud/quality masking to a loaded dataset
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Iterable, Tuple, Any, List

import geopandas as gpd
from shapely.geometry import box
from odc.algo import erase_bad, mask_cleanup
import xarray as xr

@dataclass(frozen=True)
class DefaultCloudMaskHook:
    """No-op cloud mask: returns requested bands as a dataarray without masking."""

    def get_bands(self, bands: List[str]) -> List[str]:
        return bands

    def apply(self, ds: xr.Dataset, bands: Iterable[str]) -> xr.DataArray:
        da = (
            ds[list(bands)]
            .to_dataarray(dim="band")
            .transpose(..., "band")
        )
        return da


@dataclass(frozen=True)
class SCLCloudMaskHook:
    """SCL-based masking with cleanup, matching prior behavior."""
    closing: int = 5
    opening: int = 5
    allowed_values: Tuple[int, int] = (4, 5)  # VEGETATION, NOT_VEGETATED

    def get_bands(self, bands: List[str]) -> List[str]:
        return ["scl"] + bands

    def apply(self, ds: xr.Dataset, bands: Iterable[str]) -> xr.DataArray:
        
        cloud_mask = ~ds.scl.isin(list(self.allowed_values))
        cloud_mask = mask_cleanup(cloud_mask, [("closing", self.closing), ("opening", self.opening)])
        ds_masked = erase_bad(ds[list(bands)], cloud_mask)
        da = (
            ds_masked.where(ds_masked > 0)
            .to_dataarray(dim="band")
            .transpose(..., "band")
        )
        return da
