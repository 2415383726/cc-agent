from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse


@dataclass(slots=True)
class StorageConfig:
    enabled: bool = False
    endpoint: str = ""
    bucket: str = ""
    access_key: str = ""
    secret_key: str = ""
    secure: bool = True
    public_download_base_url: str = ""
    presign_expiry_seconds: int = 3600
    ttl_days: int = 30

    def missing_required(self) -> list[str]:
        if not self.enabled:
            return []
        required = {
            "endpoint": self.endpoint,
            "bucket": self.bucket,
            "access_key": self.access_key,
            "secret_key": self.secret_key,
        }
        return [key for key, value in required.items() if not str(value or "").strip()]

    def redacted_summary(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "endpoint": self.endpoint,
            "bucket": self.bucket,
            "secure": self.secure,
            "public_download_base_url": self.public_download_base_url,
            "presign_expiry_seconds": self.presign_expiry_seconds,
            "ttl_days": self.ttl_days,
        }


class ConditionalWriteConflict(RuntimeError):
    pass

class MinioStorageClient:
    def __init__(self, config: StorageConfig):
        missing = config.missing_required()
        if missing:
            raise ValueError(f"MinIO workspace config missing: {', '.join(missing)}")
        try:
            from minio import Minio
            from minio.error import S3Error
        except Exception as exc:  # pragma: no cover - depends on packaging environment
            raise RuntimeError("minio Python package is required for workspace storage") from exc

        endpoint, secure = _minio_endpoint(config.endpoint, config.secure)
        self.config = config
        self.bucket = config.bucket
        self._s3_error = S3Error
        self.client = Minio(
            endpoint,
            access_key=config.access_key,
            secret_key=config.secret_key,
            secure=secure,
        )

    def get_json(self, key: str) -> dict[str, Any] | None:
        response = None
        try:
            response = self.client.get_object(self.bucket, key)
            content = response.read()
        except self._s3_error as exc:
            if getattr(exc, "code", "") in {"NoSuchKey", "NoSuchBucket", "NoSuchObject"}:
                return None
            raise
        finally:
            if response is not None:
                response.close()
                response.release_conn()
        if not content:
            return None
        payload = json.loads(content.decode("utf-8"))
        return payload if isinstance(payload, dict) else None
    def get_json_with_etag(self, key: str) -> tuple[dict[str, Any] | None, str | None]:
        response = None
        try:
            response = self.client.get_object(self.bucket, key)
            content = response.read()
            etag = str(response.headers.get("ETag") or response.headers.get("etag") or "").strip() or None
        except self._s3_error as exc:
            if getattr(exc, "code", "") in {"NoSuchKey", "NoSuchBucket", "NoSuchObject"}:
                return None, None
            raise
        finally:
            if response is not None:
                response.close()
                response.release_conn()
        if not content:
            return None, etag
        payload = json.loads(content.decode("utf-8"))
        return (payload if isinstance(payload, dict) else None), etag


    def put_json(self, key: str, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.client.put_object(
            self.bucket,
            key,
            BytesIO(data),
            length=len(data),
            content_type="application/json; charset=utf-8",
        )
    def put_json_conditional(
        self,
        key: str,
        payload: dict[str, Any],
        expected_etag: str | None,
    ) -> str:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Content-Length": str(len(data)),
        }
        if expected_etag is None:
            headers["If-None-Match"] = "*"
        else:
            headers["If-Match"] = expected_etag
        response = None
        try:
            response = self.client._execute(
                "PUT",
                self.bucket,
                key,
                body=data,
                headers=headers,
            )
        except self._s3_error as exc:
            if getattr(exc, "code", "") in {"PreconditionFailed", "ConditionalRequestConflict"}:
                raise ConditionalWriteConflict(f"conditional write conflict for {key}") from exc
            raise
        finally:
            if response is not None:
                response.close()
                response.release_conn()
        return str(response.headers.get("ETag") or response.headers.get("etag") or "").strip()


    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        payload = bytes(data or b"")
        self.client.put_object(
            self.bucket,
            key,
            BytesIO(payload),
            length=len(payload),
            content_type=content_type or "application/octet-stream",
        )

    def list_objects(self, prefix: str) -> list[str]:
        return [
            str(item.object_name)
            for item in self.client.list_objects(self.bucket, prefix=str(prefix or ""), recursive=True)
            if getattr(item, "object_name", None)
        ]

    def object_exists(self, key: str) -> bool:
        try:
            self.client.stat_object(self.bucket, key)
            return True
        except self._s3_error as exc:
            if getattr(exc, "code", "") in {"NoSuchKey", "NoSuchBucket", "NoSuchObject"}:
                return False
            raise

    def upload_file(self, key: str, local_path: str | Path, content_type: str = "application/octet-stream") -> None:
        self.client.fput_object(self.bucket, key, str(local_path), content_type=content_type)

    def download_file(self, key: str, local_path: str | Path) -> None:
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        self.client.fget_object(self.bucket, key, str(local_path))

    def presigned_get_url(self, key: str, expiry_seconds: int, filename: str = "", mime_type: str = "") -> str:
        headers: dict[str, str] = {}
        if filename:
            safe_name = filename.replace('"', "'")
            headers["response-content-disposition"] = f'attachment; filename="{safe_name}"'
        if mime_type:
            if mime_type.startswith("text/"):
                headers["response-content-type"] = f"{mime_type}; charset=utf-8"
            else:
                headers["response-content-type"] = mime_type
        url = self.client.presigned_get_object(
            self.bucket,
            key,
            expires=timedelta(seconds=max(1, int(expiry_seconds or 3600))),
            response_headers=headers if headers else None,
        )
        return _rewrite_public_base(url, self.config.public_download_base_url)

    def delete_object(self, key: str) -> None:
        try:
            self.client.remove_object(self.bucket, key)
        except self._s3_error as exc:
            if getattr(exc, "code", "") not in {"NoSuchKey", "NoSuchBucket", "NoSuchObject"}:
                raise


def _minio_endpoint(endpoint: str, secure: bool) -> tuple[str, bool]:
    value = str(endpoint or "").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        return parsed.netloc + parsed.path, parsed.scheme == "https"
    return value, bool(secure)


def _rewrite_public_base(url: str, public_base_url: str) -> str:
    base = str(public_base_url or "").strip().rstrip("/")
    if not base:
        return url
    parsed_url = urlparse(url)
    parsed_base = urlparse(base if "://" in base else f"https://{base}")
    return urlunparse(
        (
            parsed_base.scheme,
            parsed_base.netloc,
            parsed_url.path,
            parsed_url.params,
            parsed_url.query,
            parsed_url.fragment,
        )
    )
