"""
Abstraction to wrap both regular Zarr stores and Arraylake Zarr stores.
"""

import os
from abc import ABC, abstractmethod
from contextlib import contextmanager

import arraylake
import icechunk
import zarr
from arraylake.asyn import sync
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
        self._store = zarr.storage.FsspecStore.from_url(uri)

    def initialize(self):
        zsync(self._store.clear())

    @contextmanager
    def get_zarr_store(self):
        yield self._store

    def commit(self, message, results=None):
        # no-op
        # vanilla Zarr stores are not transactional
        pass


class ArraylakeStorage(AbstractStorage):
    zarr_version = 3

    def __init__(self, repo_name: str):
        try:
            token = os.environ["ARRAYLAKE_TOKEN"]
        except KeyError as e:
            raise ValueError("ARRAYLAKE_TOKEN environment variable is not set.") from e

        self._repo_name = repo_name
        self._client = arraylake.Client(token=token)
        self._session = None

    def initialize(self):
        try:
            self._client.delete_repo(self._repo_name, imsure=True, imreallysure=True)
        except ValueError:
            pass
        finally:
            self._repo = self._client.create_repo(self._repo_name)

    @contextmanager
    def get_zarr_store(self):
        # repo = self._client.get_repo(self._repo_name)
        async def get_storage():
            aclient = self._client.aclient
            repo_model = await aclient.get_repo_object(self._repo_name)
            credential_refresh_func = (
                aclient._maybe_get_credential_refresh_func_for_icechunk(
                    bucket=repo_model.bucket,
                    org=repo_model.org,
                    repo_name=repo_model.name,
                )
            )
            credentials = credential_refresh_func()
            return icechunk.s3_storage(
                bucket=repo_model.bucket.name,
                prefix=repo_model.prefix,
                region=repo_model.bucket.extra_config["region_name"],
                access_key_id=credentials.access_key_id if credentials else None,
                secret_access_key=(
                    credentials.secret_access_key if credentials else None
                ),
                session_token=credentials.session_token if credentials else None,
                expires_after=credentials.expires_after if credentials else None,
                # get_credentials=credential_refresh_func,
                # scatter_initial_credentials=True
            )

        storage = sync(get_storage)
        repo = icechunk.Repository.open(storage)
        repo.set_default_commit_metadata(
            {"author_name": "Ryan Abernathey", "author_email": "ryan@earthmover.io"}
        )

        self._session = repo.writable_session("main")
        with self._session.allow_pickling():
            yield self._session.store

    def commit(self, message, results=None):
        if results is not None:
            # empty tiles return nothing
            valid_results = [result for result in results if result is not None]
            valid_sessions = [
                result.session for result in valid_results if result.session is not None
            ]
            session = merge_sessions(self._session, *valid_sessions)
        else:
            session = self._session
        session.commit(message)
