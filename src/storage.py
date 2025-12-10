"""
Abstraction to wrap regular Zarr stores.
"""

import os
from abc import ABC, abstractmethod
from contextlib import contextmanager


import icechunk
import zarr
from icechunk.distributed import merge_sessions
from zarr.core.sync import sync as zsync


class AbstractStorage(ABC):
    @abstractmethod
    def initialize(self):
        pass

    @abstractmethod
    def get_zarr_store(self):
        pass

    @abstractmethod
    def commit(self, message):
        pass


class ZarrFSSpecStorage(AbstractStorage):
    zarr_version = 3

    def __init__(self, uri):
        self.uri = uri
        if uri.startswith(('file://', '/', './')) or not '://' in uri:
            # Local file system
            path = uri.replace('file://', '') if uri.startswith('file://') else uri
            self._store = zarr.storage.LocalStore(path)
        else:
            # Remote storage via fsspec
            self._store = zarr.storage.FsspecStore.from_url(uri)

    def initialize(self):
        try:
            zsync(self._store.clear())
        except FileNotFoundError:
            # Store root may not exist yet; that's fine for initialization
            pass

    @contextmanager
    def get_zarr_store(self):
        yield self._store

    def commit(self, message, results=None):
        # no-op
        # vanilla Zarr stores are not transactional
        pass


