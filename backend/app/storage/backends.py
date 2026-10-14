"""Object storage backends (local filesystem for development, S3-compatible for production).

Every object key is namespaced ``orgs/<organization_id>/…``; tenant code only ever receives a
``TenantStorage`` that refuses keys outside its own prefix (storage-layer tenant isolation).
Originals are written create-only, so an existing original can never be overwritten.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import time
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol
from urllib.parse import quote

from app.config import get_settings
from app.security.credentials import sign_payload, verify_signature


class StorageError(Exception):
    pass


class ObjectExists(StorageError):
    pass


@dataclass
class StoredObject:
    uri: str
    key: str
    size: int
    sha256: str


class StorageBackend(Protocol):
    scheme: str

    def put_file(self, key: str, path: Path, content_type: str, *, create_only: bool = False) -> StoredObject: ...
    def put_bytes(self, key: str, data: bytes, content_type: str, *, create_only: bool = False) -> StoredObject: ...
    def download_to(self, key: str, path: Path) -> None: ...
    def read_bytes(self, key: str) -> bytes: ...
    def iter_chunks(self, key: str, chunk_size: int = 1 << 20) -> Iterator[bytes]: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def delete_prefix(self, prefix: str) -> int: ...
    def signed_url(self, key: str, *, filename: str | None, content_type: str | None, ttl: int, inline: bool) -> str: ...


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_key(key: str) -> str:
    if key.startswith("/") or ".." in key.split("/") or "\\" in key or not key:
        raise StorageError(f"unsafe storage key: {key!r}")
    return key


class LocalStorage:
    scheme = "local"

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / _safe_key(key)).resolve()
        if self.root not in p.parents:
            raise StorageError("key escapes storage root")
        return p

    def put_file(self, key: str, path: Path, content_type: str, *, create_only: bool = False) -> StoredObject:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if create_only and dest.exists():
            raise ObjectExists(key)
        tmp = dest.with_name(dest.name + f".tmp-{uuid.uuid4().hex}")
        shutil.copyfile(path, tmp)
        if create_only:
            try:
                dest.hardlink_to(tmp)  # atomic create-only: fails if dest already exists
            except FileExistsError as e:
                raise ObjectExists(key) from e
            finally:
                tmp.unlink(missing_ok=True)
        else:
            tmp.replace(dest)
        return StoredObject(f"local://{key}", key, dest.stat().st_size, _sha256_file(dest))

    def put_bytes(self, key: str, data: bytes, content_type: str, *, create_only: bool = False) -> StoredObject:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if create_only:
            try:
                with dest.open("xb") as f:
                    f.write(data)
            except FileExistsError as e:
                raise ObjectExists(key) from e
        else:
            tmp = dest.with_name(dest.name + f".tmp-{uuid.uuid4().hex}")
            tmp.write_bytes(data)
            tmp.replace(dest)
        return StoredObject(f"local://{key}", key, len(data), hashlib.sha256(data).hexdigest())

    def download_to(self, key: str, path: Path) -> None:
        shutil.copyfile(self._path(key), path)

    def read_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def iter_chunks(self, key: str, chunk_size: int = 1 << 20) -> Iterator[bytes]:
        with self._path(key).open("rb") as f:
            yield from iter(lambda: f.read(chunk_size), b"")

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def local_path(self, key: str) -> Path:
        return self._path(key)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> int:
        p = self._path(prefix.rstrip("/"))
        if not p.exists():
            return 0
        n = sum(1 for f in p.rglob("*") if f.is_file())
        shutil.rmtree(p, ignore_errors=True)
        return n

    def signed_url(self, key: str, *, filename: str | None, content_type: str | None, ttl: int, inline: bool) -> str:
        payload = json.dumps(
            {"k": key, "e": int(time.time()) + ttl, "f": filename, "t": content_type, "i": inline},
            separators=(",", ":"),
        )
        token = urlsafe_b64encode(payload.encode()).decode().rstrip("=")
        return f"{get_settings().public_base_url}/v1/files/{token}.{sign_payload(token)}"


def decode_signed_token(token: str) -> dict:
    """Validate a local signed URL token -> payload dict. Raises StorageError."""
    try:
        body, sig = token.rsplit(".", 1)
    except ValueError as e:
        raise StorageError("malformed token") from e
    if not verify_signature(body, sig):
        raise StorageError("bad signature")
    payload = json.loads(urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    if payload["e"] < time.time():
        raise StorageError("expired")
    return payload


class S3Storage:
    """S3 / Cloudflare R2 / MinIO. Uses conditional writes (If-None-Match) for create-only."""

    scheme = "s3"

    def __init__(self):
        import boto3
        from botocore.config import Config

        s = get_settings()
        if not s.s3_bucket:
            raise StorageError("BDNA_S3_BUCKET is required for the s3 storage backend")
        self.bucket = s.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url or None,
            region_name=s.s3_region,
            aws_access_key_id=s.s3_access_key_id or None,
            aws_secret_access_key=s.s3_secret_access_key or None,
            config=Config(signature_version="s3v4", retries={"max_attempts": 5, "mode": "standard"}),
        )

    def _uri(self, key: str) -> str:
        return f"s3://{self.bucket}/{key}"

    def put_file(self, key: str, path: Path, content_type: str, *, create_only: bool = False) -> StoredObject:
        sha = _sha256_file(path)
        with path.open("rb") as f:
            self._put(key, f, content_type, create_only, sha)
        return StoredObject(self._uri(key), key, path.stat().st_size, sha)

    def put_bytes(self, key: str, data: bytes, content_type: str, *, create_only: bool = False) -> StoredObject:
        sha = hashlib.sha256(data).hexdigest()
        self._put(key, data, content_type, create_only, sha)
        return StoredObject(self._uri(key), key, len(data), sha)

    def _put(self, key: str, body: BinaryIO | bytes, content_type: str, create_only: bool, sha: str) -> None:
        from botocore.exceptions import ClientError

        kw = {"Bucket": self.bucket, "Key": _safe_key(key), "Body": body, "ContentType": content_type,
              "Metadata": {"sha256": sha}}
        if create_only:
            kw["IfNoneMatch"] = "*"
        try:
            self.client.put_object(**kw)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("PreconditionFailed", "412"):
                raise ObjectExists(key) from e
            raise StorageError(str(e)) from e

    def download_to(self, key: str, path: Path) -> None:
        self.client.download_file(self.bucket, _safe_key(key), str(path))

    def read_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=_safe_key(key))["Body"].read()

    def iter_chunks(self, key: str, chunk_size: int = 1 << 20) -> Iterator[bytes]:
        body = self.client.get_object(Bucket=self.bucket, Key=_safe_key(key))["Body"]
        yield from body.iter_chunks(chunk_size)

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=_safe_key(key))
            return True
        except ClientError:
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=_safe_key(key))

    def delete_prefix(self, prefix: str) -> int:
        n = 0
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=_safe_key(prefix)):
            objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            for i in range(0, len(objs), 1000):
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": objs[i : i + 1000]})
            n += len(objs)
        return n

    def signed_url(self, key: str, *, filename: str | None, content_type: str | None, ttl: int, inline: bool) -> str:
        params = {"Bucket": self.bucket, "Key": _safe_key(key)}
        if filename:
            disp = "inline" if inline else "attachment"
            params["ResponseContentDisposition"] = f"{disp}; filename*=UTF-8''{quote(filename)}"
        if content_type:
            params["ResponseContentType"] = content_type
        return self.client.generate_presigned_url("get_object", Params=params, ExpiresIn=ttl)


_backend: StorageBackend | None = None


def backend() -> StorageBackend:
    global _backend
    if _backend is None:
        s = get_settings()
        _backend = S3Storage() if s.storage_backend == "s3" else LocalStorage(Path(s.storage_local_root))
    return _backend


def reset_backend() -> None:
    global _backend
    _backend = None


def key_from_uri(uri: str) -> str:
    if uri.startswith("local://"):
        return uri[len("local://") :]
    if uri.startswith("s3://"):
        return uri.split("/", 3)[3]
    raise StorageError(f"unsupported storage uri {uri!r}")


class TenantStorage:
    """Storage facade bound to one organization. Rejects any key outside ``orgs/<org_id>/``."""

    def __init__(self, org_id: uuid.UUID):
        self.org_id = org_id
        self.prefix = f"orgs/{org_id}/"
        self.b = backend()

    def _check(self, key: str) -> str:
        if not key.startswith(self.prefix):
            raise StorageError("storage key outside tenant namespace")
        return key

    def key_for_uri(self, uri: str) -> str:
        return self._check(key_from_uri(uri))

    # Key builders -----------------------------------------------------------------------
    def original_key(self, brand_id: uuid.UUID, asset_id: uuid.UUID, filename: str) -> str:
        return f"{self.prefix}brands/{brand_id}/assets/{asset_id}/original/{filename}"

    def derivative_key(self, brand_id: uuid.UUID, asset_id: uuid.UUID, kind: str, name: str) -> str:
        return f"{self.prefix}brands/{brand_id}/assets/{asset_id}/derivatives/{kind}/{name}"

    def asset_derivatives_prefix(self, brand_id: uuid.UUID, asset_id: uuid.UUID) -> str:
        return f"{self.prefix}brands/{brand_id}/assets/{asset_id}/derivatives/"

    def asset_prefix(self, brand_id: uuid.UUID, asset_id: uuid.UUID) -> str:
        return f"{self.prefix}brands/{brand_id}/assets/{asset_id}/"

    def export_key(self, export_id: uuid.UUID) -> str:
        return f"{self.prefix}exports/{export_id}.zip"

    def import_key(self, import_id: uuid.UUID) -> str:
        return f"{self.prefix}imports/{import_id}.zip"

    def context_key(self, package_id: uuid.UUID) -> str:
        return f"{self.prefix}context/{package_id}.zip"

    # Operations -------------------------------------------------------------------------
    def put_file(self, key: str, path: Path, content_type: str, *, create_only: bool = False) -> StoredObject:
        return self.b.put_file(self._check(key), path, content_type, create_only=create_only)

    def put_bytes(self, key: str, data: bytes, content_type: str, *, create_only: bool = False) -> StoredObject:
        return self.b.put_bytes(self._check(key), data, content_type, create_only=create_only)

    def download_to(self, key: str, path: Path) -> None:
        self.b.download_to(self._check(key), path)

    def read_bytes(self, key: str) -> bytes:
        return self.b.read_bytes(self._check(key))

    def exists(self, key: str) -> bool:
        return self.b.exists(self._check(key))

    def delete(self, key: str) -> None:
        self.b.delete(self._check(key))

    def delete_prefix(self, prefix: str) -> int:
        return self.b.delete_prefix(self._check(prefix))

    def signed_url(
        self, key: str, *, filename: str | None = None, content_type: str | None = None, inline: bool = True,
        ttl: int | None = None,
    ) -> str:
        return self.b.signed_url(
            self._check(key), filename=filename, content_type=content_type,
            ttl=ttl or get_settings().signed_url_ttl_seconds, inline=inline,
        )

    def signed_url_expiry(self, ttl: int | None = None) -> str:
        return (dt.datetime.now(dt.UTC) + dt.timedelta(seconds=ttl or get_settings().signed_url_ttl_seconds)).isoformat()
