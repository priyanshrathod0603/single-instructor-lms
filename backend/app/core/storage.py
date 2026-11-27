"""Object Storage Client Abstraction for Cloudflare R2 and AWS S3.

Architecture Specifications:
- docs/backend/15-FILE-MEDIA-ARCHITECTURE.md (Section 1)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK401)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-009)

Features:
1. Standard AWS Signature Version 4 (SigV4) calculation using Python stdlib (hmac/hashlib).
2. Generates short-lived presigned PUT URLs (15-minute TTL) for direct client-to-storage ingestion.
3. Generates presigned GET URLs for protected downloads.
4. Provides deterministic in-memory storage driver for isolated unit and integration testing.
"""

from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _sign(key: bytes, msg: str) -> bytes:
    """Computes HMAC-SHA256 signature byte digest."""
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(key: str, date_stamp: str, region_name: str, service_name: str) -> bytes:
    """Derives AWS SigV4 signing key."""
    k_date = _sign(("AWS4" + key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region_name)
    k_service = _sign(k_region, service_name)
    k_signing = _sign(k_service, "aws4_request")
    return k_signing


# Shared in-memory buffer for test/dev object persistence across StorageClient instances
_shared_in_memory_storage: dict[str, tuple[bytes, str]] = {}


class StorageClient:
    """Storage client managing direct presigned S3/R2 uploads and object retrieval."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.bucket = self.settings.STORAGE_BUCKET_NAME
        self.region = self.settings.STORAGE_REGION or "auto"
        self.endpoint_url = self.settings.STORAGE_ENDPOINT_URL
        self.access_key = self.settings.STORAGE_ACCESS_KEY_ID or "mock-access-key"
        self.secret_key = (
            self.settings.STORAGE_SECRET_ACCESS_KEY.get_secret_value()
            if self.settings.STORAGE_SECRET_ACCESS_KEY
            else "mock-secret-key"
        )
        self._in_memory_storage = _shared_in_memory_storage
        self._local_storage_dir = Path(__file__).resolve().parents[2] / ".local_storage"

    def _should_persist_local_disk(self) -> bool:
        """Persist local non-production objects to disk outside automated pytest runs."""
        if self.is_remote_configured or self.settings.is_production:
            return False
        if self.settings.ENVIRONMENT.lower() == "test":
            return False
        if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
            return False
        return True

    def _resolve_local_paths(self, file_key: str) -> Tuple[Path, Path]:
        """Resolve local object & metadata paths with strict containment guard."""
        clean_key = file_key.lstrip("/")
        if not clean_key or ".." in Path(clean_key).parts:
            raise ValueError(f"Invalid storage key path: {file_key}")
        base_dir = self._local_storage_dir.resolve()
        obj_path = (base_dir / clean_key).resolve()
        if base_dir != obj_path and base_dir not in obj_path.parents:
            raise ValueError(f"Storage key escapes local directory: {file_key}")
        meta_path = Path(f"{obj_path}.meta.json")
        return obj_path, meta_path

    def _write_local_disk_object(self, file_key: str, data: bytes, content_type: str) -> None:
        if not self._should_persist_local_disk():
            return
        obj_path, meta_path = self._resolve_local_paths(file_key)
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        obj_path.write_bytes(data)
        meta_path.write_text(json.dumps({"content_type": content_type}), encoding="utf-8")

    def _read_local_disk_object(self, file_key: str) -> Optional[Tuple[bytes, str]]:
        if not self._should_persist_local_disk():
            return None
        try:
            obj_path, meta_path = self._resolve_local_paths(file_key)
        except ValueError:
            return None
        if not obj_path.is_file():
            return None
        content_type = "application/octet-stream"
        if meta_path.is_file():
            try:
                content_type = json.loads(meta_path.read_text(encoding="utf-8")).get("content_type", content_type)
            except Exception:
                pass
        data = obj_path.read_bytes()
        self._in_memory_storage[file_key] = (data, content_type)
        return data, content_type

    def _delete_local_disk_object(self, file_key: str) -> bool:
        if not self._should_persist_local_disk():
            return False
        try:
            obj_path, meta_path = self._resolve_local_paths(file_key)
        except ValueError:
            return False
        removed = False
        if obj_path.is_file():
            obj_path.unlink()
            removed = True
        if meta_path.is_file():
            meta_path.unlink()
        return removed

    def _get_endpoint_and_uri(self, file_key: str, for_upload: bool = True) -> Tuple[str, str, str]:
        """Compute host, canonical URI, and base URL supporting both path and virtual-host styles.

        Returns:
            Tuple of (host, canonical_uri, base_url).
        """
        clean_key = file_key.lstrip("/")
        quoted_key = urllib.parse.quote(clean_key)

        if self.endpoint_url:
            clean_endpoint = self.endpoint_url.rstrip("/")
            parsed = urllib.parse.urlparse(clean_endpoint)
            host = parsed.netloc or parsed.path

            # Virtual-hosted style: bucket is prefix of host (e.g. mybucket.r2.cloudflarestorage.com)
            if parsed.netloc.startswith(f"{self.bucket}."):
                canonical_uri = f"/{quoted_key}"
                base_url = f"{clean_endpoint}/{quoted_key}"
            else:
                # Path style: bucket is part of URL path (e.g. http://localhost:9000/mybucket/key)
                canonical_uri = f"/{self.bucket}/{quoted_key}"
                base_url = f"{clean_endpoint}/{self.bucket}/{quoted_key}"
        elif not self.is_remote_configured and not self.settings.is_production:
            backend_url = (self.settings.BACKEND_URL or "http://localhost:8000").rstrip("/")
            api_prefix = self.settings.API_V1_STR.rstrip("/")
            parsed = urllib.parse.urlparse(backend_url)
            host = parsed.netloc or "localhost:8000"
            subpath = "upload" if for_upload else "download"
            canonical_uri = f"{api_prefix}/media/storage/{subpath}/{quoted_key}"
            base_url = f"{backend_url}{api_prefix}/media/storage/{subpath}/{quoted_key}"
        else:
            # Default AWS S3 virtual-hosted style
            host = f"{self.bucket}.s3.{self.region}.amazonaws.com"
            canonical_uri = f"/{quoted_key}"
            base_url = f"https://{host}/{quoted_key}"

        return host, canonical_uri, base_url

    def generate_presigned_upload_url(
        self,
        file_key: str,
        mime_type: str,
        file_size_bytes: int,
        expires_in_seconds: int = 900,
    ) -> Tuple[str, dict[str, str]]:
        """Generate a presigned PUT URL and required headers for direct binary upload.

        Args:
            file_key: Unique object storage key (e.g. 'raw-videos/uuid/video.mp4').
            mime_type: Content-Type string to be enforced by the storage bucket.
            file_size_bytes: Expected file size.
            expires_in_seconds: URL lifespan in seconds (default: 900 / 15 minutes).

        Returns:
            Tuple of (presigned_url, required_headers_dict).
        """
        if self.settings.is_production and not self.is_remote_configured:
            raise RuntimeError("Remote storage credentials are required to generate presigned upload URLs in production.")

        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        host, canonical_uri, base_url = self._get_endpoint_and_uri(file_key, for_upload=True)

        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        signed_headers = "content-type;host"

        # Canonical query parameters
        query_params = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"{self.access_key}/{credential_scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(expires_in_seconds),
            "X-Amz-SignedHeaders": signed_headers,
        }
        canonical_query = urllib.parse.urlencode(sorted(query_params.items()))

        canonical_headers = f"content-type:{mime_type}\nhost:{host}\n"
        canonical_request = (
            f"PUT\n"
            f"{canonical_uri}\n"
            f"{canonical_query}\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"UNSIGNED-PAYLOAD"
        )

        string_to_sign = (
            f"AWS4-HMAC-SHA256\n"
            f"{amz_date}\n"
            f"{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )

        signing_key = _get_signature_key(self.secret_key, date_stamp, self.region, "s3")
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        final_url = f"{base_url}?{canonical_query}&X-Amz-Signature={signature}"
        required_headers = {
            "Content-Type": mime_type,
        }

        return final_url, required_headers

    def generate_presigned_download_url(
        self,
        file_key: str,
        expires_in_seconds: int = 7200,
    ) -> str:
        """Generate a presigned GET URL for object retrieval."""
        if self.settings.is_production and not self.is_remote_configured:
            raise RuntimeError("Remote storage credentials are required to generate presigned download URLs in production.")

        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        host, canonical_uri, base_url = self._get_endpoint_and_uri(file_key, for_upload=False)

        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        signed_headers = "host"

        query_params = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"{self.access_key}/{credential_scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(expires_in_seconds),
            "X-Amz-SignedHeaders": signed_headers,
        }
        canonical_query = urllib.parse.urlencode(sorted(query_params.items()))
        canonical_headers = f"host:{host}\n"
        canonical_request = (
            f"GET\n"
            f"{canonical_uri}\n"
            f"{canonical_query}\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"UNSIGNED-PAYLOAD"
        )

        string_to_sign = (
            f"AWS4-HMAC-SHA256\n"
            f"{amz_date}\n"
            f"{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )
        signing_key = _get_signature_key(self.secret_key, date_stamp, self.region, "s3")
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        return f"{base_url}?{canonical_query}&X-Amz-Signature={signature}"

    @property
    def is_remote_configured(self) -> bool:
        """Check if remote S3 / Cloudflare R2 credentials are configured."""
        if not self.access_key or self.access_key in ("mock-access-key", "test-key"):
            return False
        if not self.secret_key or self.secret_key in ("mock-secret-key", "test-secret"):
            return False
        return bool(self.bucket)

    def _execute_signed_request(
        self,
        method: str,
        file_key: str,
        data: Optional[bytes] = None,
        content_type: Optional[str] = None,
        byte_range: Optional[str] = None,
    ) -> Tuple[int, dict[str, str], bytes]:
        """Execute an AWS SigV4 signed HTTP request against S3/R2 REST API."""
        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        host, canonical_uri, url = self._get_endpoint_and_uri(file_key, for_upload=(method.upper() in ("PUT", "POST")))

        payload_bytes = data or b""
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()

        headers: dict[str, str] = {
            "Host": host,
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
        }
        if content_type:
            headers["Content-Type"] = content_type
        if byte_range:
            headers["Range"] = byte_range

        # Build SigV4 authorization header
        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        sorted_header_keys = sorted(k.lower() for k in headers.keys())
        signed_headers = ";".join(sorted_header_keys)
        canonical_headers = "".join(f"{k}:{headers.get(k, headers.get(k.lower(), headers.get(k.title(), ''))).strip()}\n" for k in sorted_header_keys)

        canonical_request = (
            f"{method.upper()}\n"
            f"{canonical_uri}\n"
            f"\n"
            f"{canonical_headers}"
            f"{signed_headers}\n"
            f"{payload_hash}"
        )

        string_to_sign = (
            f"AWS4-HMAC-SHA256\n"
            f"{amz_date}\n"
            f"{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )

        signing_key = _get_signature_key(self.secret_key, date_stamp, self.region, "s3")
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        headers["Authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

        req = urllib.request.Request(url, data=payload_bytes if method in ("PUT", "POST") else None, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as response:
                resp_code = response.getcode()
                resp_headers = dict(response.info())
                resp_body = response.read()
                return resp_code, resp_headers, resp_body
        except urllib.error.HTTPError as err:
            return err.code, dict(err.headers), err.read()

    def head_object(self, file_key: str) -> Optional[dict[str, Any]]:
        """Retrieve object metadata (size, content-type) or return None if not found."""
        if self.is_remote_configured:
            code, headers, _ = self._execute_signed_request("HEAD", file_key)
            if code == 200:
                content_len = int(headers.get("Content-Length", headers.get("content-length", 0)))
                content_type = headers.get("Content-Type", headers.get("content-type", "application/octet-stream"))
                return {
                    "exists": True,
                    "size": content_len,
                    "content_type": content_type,
                    "etag": headers.get("ETag", headers.get("etag", "")).strip('"'),
                }
            return None

        if self.settings.is_production:
            raise RuntimeError("Remote storage credentials are required in production; in-memory fallback is prohibited.")

        # In-memory / local-dev disk storage check for non-production environments
        if file_key in self._in_memory_storage:
            data, content_type = self._in_memory_storage[file_key]
            return {
                "exists": True,
                "size": len(data),
                "content_type": content_type,
                "etag": hashlib.md5(data).hexdigest(),
            }
        disk_obj = self._read_local_disk_object(file_key)
        if disk_obj is not None:
            data, content_type = disk_obj
            return {
                "exists": True,
                "size": len(data),
                "content_type": content_type,
                "etag": hashlib.md5(data).hexdigest(),
            }
        return None

    def object_exists(self, file_key: str) -> bool:
        """Check whether object exists in remote storage or local buffer."""
        meta = self.head_object(file_key)
        return meta is not None and meta.get("exists", False)

    def put_object(self, file_key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        """Store binary object in remote storage or local buffer."""
        if self.is_remote_configured:
            code, _, body = self._execute_signed_request("PUT", file_key, data=data, content_type=content_type)
            if code not in (200, 201, 204):
                raise RuntimeError(f"Failed to put object to remote storage: HTTP {code} - {body.decode('utf-8', errors='replace')}")
            return

        if self.settings.is_production:
            raise RuntimeError("Remote storage credentials are required in production; in-memory fallback is prohibited.")

        self._in_memory_storage[file_key] = (data, content_type)
        self._write_local_disk_object(file_key, data, content_type)

    def get_object(self, file_key: str) -> bytes:
        """Retrieve binary object bytes from storage without fallback to sample data."""
        if self.is_remote_configured:
            code, _, body = self._execute_signed_request("GET", file_key)
            if code == 200:
                return body
            raise KeyError(f"Storage object not found: {file_key}")

        if self.settings.is_production:
            raise KeyError(f"Remote storage credentials are required in production; in-memory fallback is prohibited.")

        if file_key in self._in_memory_storage:
            return self._in_memory_storage[file_key][0]

        disk_obj = self._read_local_disk_object(file_key)
        if disk_obj is not None:
            return disk_obj[0]

        raise KeyError(f"Storage object not found: {file_key}")

    def get_object_prefix(self, file_key: str, length: int = 512) -> bytes:
        """Read only a small leading range for binary signature validation.

        This is intentionally separate from ``get_object`` so upload
        confirmation never copies a multi-gigabyte video into application RAM.
        """
        if length <= 0:
            return b""
        if self.is_remote_configured:
            code, _, body = self._execute_signed_request(
                "GET", file_key, byte_range=f"bytes=0-{length - 1}"
            )
            if code in (200, 206):
                return body[:length]
            raise KeyError(f"Storage object not found: {file_key}")
        if self.settings.is_production:
            raise KeyError("Remote storage credentials are required in production.")
        if file_key in self._in_memory_storage:
            return self._in_memory_storage[file_key][0][:length]
        disk_obj = self._read_local_disk_object(file_key)
        if disk_obj is not None:
            return disk_obj[0][:length]
        raise KeyError(f"Storage object not found: {file_key}")

    def delete_object(self, file_key: str) -> bool:
        """Delete object from storage."""
        if self.is_remote_configured:
            code, _, _ = self._execute_signed_request("DELETE", file_key)
            return code in (200, 204)

        if self.settings.is_production:
            raise RuntimeError("Remote storage credentials are required in production; in-memory fallback is prohibited.")

        removed = False
        if file_key in self._in_memory_storage:
            del self._in_memory_storage[file_key]
            removed = True
        if self._delete_local_disk_object(file_key):
            removed = True
        return removed

    def download_file(self, file_key: str, destination_path: Path) -> None:
        """Download binary object from storage directly to destination file on disk."""
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if self.is_remote_configured:
            code, _, body = self._execute_signed_request("GET", file_key)
            if code == 200:
                destination_path.write_bytes(body)
                return
            raise KeyError(f"Storage object not found: {file_key}")

        if self.settings.is_production:
            raise KeyError("Remote storage credentials are required in production; in-memory fallback is prohibited.")

        if file_key in self._in_memory_storage:
            data, _ = self._in_memory_storage[file_key]
            destination_path.write_bytes(data)
            return

        disk_obj = self._read_local_disk_object(file_key)
        if disk_obj is not None:
            destination_path.write_bytes(disk_obj[0])
            return

        raise KeyError(f"Storage object not found: {file_key}")

    def upload_file(self, file_key: str, source_path: Path, content_type: str = "application/octet-stream") -> None:
        """Upload a local file directly to storage."""
        if not source_path.exists():
            raise FileNotFoundError(f"Local file to upload does not exist: {source_path}")
        data = source_path.read_bytes()
        self.put_object(file_key, data, content_type=content_type)

    def upload_directory(self, local_dir: Path, target_prefix: str) -> list[str]:
        """Upload an entire directory of files (e.g. HLS variants, manifests, segments) to storage.

        Args:
            local_dir: Root directory on local disk.
            target_prefix: Storage key prefix (e.g. 'media/{media_id}/hls').

        Returns:
            List of uploaded storage object keys.
        """
        if not local_dir.exists() or not local_dir.is_dir():
            raise NotADirectoryError(f"Directory not found: {local_dir}")

        uploaded_keys: list[str] = []
        clean_prefix = target_prefix.strip("/")

        for file_path in sorted(local_dir.rglob("*")):
            if not file_path.is_file():
                continue
            relative_rel = file_path.relative_to(local_dir).as_posix()
            storage_key = f"{clean_prefix}/{relative_rel}"

            # Infer content type
            if file_path.name.endswith(".m3u8"):
                ct = "application/vnd.apple.mpegurl"
            elif file_path.name.endswith(".ts"):
                ct = "video/MP2T"
            elif file_path.name.endswith(".mp4"):
                ct = "video/mp4"
            else:
                ct = "application/octet-stream"

            self.upload_file(storage_key, file_path, content_type=ct)
            uploaded_keys.append(storage_key)

        return uploaded_keys
