"""Where an archived run goes, and how to read it back (Item 3, leg 4).

Two implementations behind one small interface:

* :class:`S3ObjectStore` — DigitalOcean Spaces, which is S3-compatible, reached
  through ``boto3``. This is the real destination.
* :class:`LocalObjectStore` — a directory. Not a test double: it is the honest
  destination when the archive goes to an attached volume or a mounted drive,
  and it is what makes the whole leg testable without credentials or network.

The interface is four methods because four are all the leg needs: put an object,
stream it back, ask whether it exists, list a prefix. Anything else — lifecycle
rules, ACLs, multipart tuning — is the bucket's configuration and belongs with
whoever provisions it, not in the pipeline that writes to it.

**Reading back is not optional.** :meth:`ObjectStore.read_stream` exists because
verification after upload means re-reading the bytes that landed, not trusting
the ``PutObject`` that claimed to write them. An ETag comparison would have been
cheaper and would have verified S3's opinion of its own metadata; the storage-v2
archive module already established the house rule for this class of check —
verify against a *fresh* read, never against numbers remembered from the write —
and this leg follows it (:mod:`g3o.run.archive`).

``boto3`` is an optional dependency, imported at first use with an install
instruction rather than declared in ``pyproject.toml``: it is needed on the
droplet and nowhere else, and every test in this repo runs against the local
store.
"""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

#: Spaces credentials and endpoint. Named here so the orchestrator has exactly
#: one place that knows how object-store secrets reach the process — the same
#: discipline ``g3o.common.credentials`` applies to the provider API keys.
SPACES_KEY_ENV_VAR = "SPACES_KEY"
SPACES_SECRET_ENV_VAR = "SPACES_SECRET"
SPACES_ENDPOINT_ENV_VAR = "SPACES_ENDPOINT"
SPACES_REGION_ENV_VAR = "SPACES_REGION"

#: Read size for streaming verification. Large enough that hashing a multi-GB tar
#: is not syscall-bound, small enough that a shard tar never has to fit in RAM.
CHUNK_BYTES = 1024 * 1024


class ObjectStoreError(RuntimeError):
    """The object store refused, or could not be reached."""


class ObjectStore(Protocol):
    """Put an object, read it back, ask if it is there, list what is."""

    uri: str

    def put(self, key: str, path: Path) -> None: ...

    def read_stream(self, key: str) -> Iterator[bytes]: ...

    def exists(self, key: str) -> bool: ...

    def list_keys(self, prefix: str = "") -> list[str]: ...


class LocalObjectStore:
    """A directory tree addressed by key. Keys are ``/``-separated, always.

    Used for an archive that goes to an attached volume or a mounted drive, and
    for every test in this suite. Writes land on a temp file and are moved into
    place with :func:`os.replace`, so a half-written object is never visible
    under its final name — the same property the S3 store gets for free from
    ``PutObject`` being atomic.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.uri = self.root.as_uri() if self.root.is_absolute() else str(self.root)

    def _path(self, key: str) -> Path:
        # Key separators are '/' by contract; on Windows this still produces a
        # valid nested path, and it keeps a key identical across both stores.
        return self.root.joinpath(*key.split("/"))

    def put(self, key: str, path: Path) -> None:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(f"{dest.name}.tmp.{os.getpid()}")
        try:
            shutil.copyfile(path, tmp)
            os.replace(tmp, dest)
        except OSError as exc:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise ObjectStoreError(f"could not write {dest}: {exc}") from exc

    def read_stream(self, key: str) -> Iterator[bytes]:
        path = self._path(key)
        try:
            with open(path, "rb") as handle:
                while True:
                    chunk = handle.read(CHUNK_BYTES)
                    if not chunk:
                        return
                    yield chunk
        except OSError as exc:
            raise ObjectStoreError(f"could not read {path}: {exc}") from exc

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list_keys(self, prefix: str = "") -> list[str]:
        base = self._path(prefix) if prefix else self.root
        if not base.exists():
            return []
        if base.is_file():
            return [prefix]
        return sorted(
            "/".join(p.relative_to(self.root).parts)
            for p in base.rglob("*")
            if p.is_file()
        )


class S3ObjectStore:
    """DigitalOcean Spaces (or any S3-compatible endpoint), via ``boto3``.

    The credentials are read once, at construction, and are never stored anywhere
    this orchestrator writes: the archive record carries the bucket, the endpoint
    and ``sha256(secret)[:8]``, exactly as the run manifest carries a key
    fingerprint rather than a key (§3.3).
    """

    def __init__(
        self,
        bucket: str,
        *,
        prefix: str = "",
        endpoint_url: str | None = None,
        region: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.endpoint_url = endpoint_url or os.environ.get(SPACES_ENDPOINT_ENV_VAR)
        self.region = region or os.environ.get(SPACES_REGION_ENV_VAR) or "us-east-1"
        self._access_key = access_key or os.environ.get(SPACES_KEY_ENV_VAR)
        self._secret_key = secret_key or os.environ.get(SPACES_SECRET_ENV_VAR)
        if not self.endpoint_url:
            raise ObjectStoreError(
                f"no endpoint for bucket {bucket!r}. Set {SPACES_ENDPOINT_ENV_VAR} "
                f"(e.g. https://fra1.digitaloceanspaces.com) or pass --spaces-endpoint."
            )
        if not (self._access_key and self._secret_key):
            raise ObjectStoreError(
                f"Spaces credentials are unset. Set {SPACES_KEY_ENV_VAR} and "
                f"{SPACES_SECRET_ENV_VAR} in the environment; they are never passed "
                f"as arguments, which would put the secret in `ps` and in shell history."
            )
        self.uri = f"s3://{bucket}/{self.prefix}" if self.prefix else f"s3://{bucket}"
        self._client = self._make_client()

    def _make_client(self) -> Any:
        try:
            import boto3  # noqa: PLC0415 - optional dependency, droplet-only
        except ImportError as exc:  # pragma: no cover - exercised on the droplet
            raise ObjectStoreError(
                "boto3 is not installed, and it is what talks to Spaces. "
                "`pip install boto3` on the machine running the archive leg. It is "
                "deliberately not a pipeline dependency: nothing but this leg needs "
                "it, and the pipeline itself must stay installable without it."
            ) from exc
        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        )

    def _full_key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def put(self, key: str, path: Path) -> None:
        try:
            self._client.upload_file(str(path), self.bucket, self._full_key(key))
        except Exception as exc:  # noqa: BLE001 - botocore raises a wide family
            raise ObjectStoreError(
                f"upload of {path} to s3://{self.bucket}/{self._full_key(key)} failed: {exc}"
            ) from exc

    def read_stream(self, key: str) -> Iterator[bytes]:
        try:
            body = self._client.get_object(
                Bucket=self.bucket, Key=self._full_key(key)
            )["Body"]
        except Exception as exc:  # noqa: BLE001
            raise ObjectStoreError(
                f"could not read s3://{self.bucket}/{self._full_key(key)}: {exc}"
            ) from exc
        try:
            while True:
                chunk = body.read(CHUNK_BYTES)
                if not chunk:
                    return
                yield chunk
        finally:
            body.close()

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=self._full_key(key))
        except Exception:  # noqa: BLE001 - a 404 is an answer, not an error
            return False
        return True

    def list_keys(self, prefix: str = "") -> list[str]:
        full = self._full_key(prefix) if prefix else self.prefix
        keys: list[str] = []
        token: str | None = None
        while True:
            kwargs: dict[str, Any] = {"Bucket": self.bucket, "Prefix": full}
            if token:
                kwargs["ContinuationToken"] = token
            try:
                page = self._client.list_objects_v2(**kwargs)
            except Exception as exc:  # noqa: BLE001
                raise ObjectStoreError(f"could not list s3://{self.bucket}/{full}: {exc}") from exc
            for item in page.get("Contents", ()):
                key = item["Key"]
                if self.prefix and key.startswith(f"{self.prefix}/"):
                    key = key[len(self.prefix) + 1 :]
                keys.append(key)
            if not page.get("IsTruncated"):
                return sorted(keys)
            token = page.get("NextContinuationToken")

    def describe(self) -> dict[str, Any]:
        """Recordable description — bucket, endpoint, key fingerprint. No secret."""
        from g3o.common.credentials import fingerprint

        return {
            "kind": "s3",
            "bucket": self.bucket,
            "prefix": self.prefix,
            "endpoint": self.endpoint_url,
            "region": self.region,
            "access_key_fingerprint": fingerprint(self._access_key),
        }


def store_from_uri(uri: str, **kwargs: Any) -> ObjectStore:
    """Build a store from ``s3://bucket/prefix``, ``file:///path``, or a path.

    A bare path is accepted because that is what an operator types for a mounted
    volume, and refusing it would only teach them to type ``file://`` in front of
    a Windows path, which is its own small disaster.
    """
    parts = urlsplit(uri)
    if parts.scheme in ("s3", "spaces"):
        bucket = parts.netloc
        if not bucket:
            raise ObjectStoreError(f"{uri!r} names no bucket (expected s3://bucket/prefix).")
        return S3ObjectStore(bucket, prefix=parts.path.lstrip("/"), **kwargs)
    if parts.scheme == "file":
        # urlsplit puts a Windows drive letter in `netloc` for file://C:/... —
        # rejoining them keeps both platforms' spellings working.
        raw = f"{parts.netloc}{parts.path}" if parts.netloc else parts.path
        return LocalObjectStore(Path(raw))
    if parts.scheme and len(parts.scheme) > 1:
        raise ObjectStoreError(
            f"unsupported destination scheme {parts.scheme!r} in {uri!r}. "
            f"Use s3://bucket/prefix, file:///path, or a plain directory path."
        )
    return LocalObjectStore(Path(uri))


def describe_store(store: ObjectStore) -> dict[str, Any]:
    """A record-safe description of any store."""
    describe = getattr(store, "describe", None)
    if callable(describe):
        return describe()
    return {"kind": "local", "uri": getattr(store, "uri", str(store))}


__all__ = [
    "CHUNK_BYTES",
    "SPACES_ENDPOINT_ENV_VAR",
    "SPACES_KEY_ENV_VAR",
    "SPACES_REGION_ENV_VAR",
    "SPACES_SECRET_ENV_VAR",
    "LocalObjectStore",
    "ObjectStore",
    "ObjectStoreError",
    "S3ObjectStore",
    "describe_store",
    "store_from_uri",
]
