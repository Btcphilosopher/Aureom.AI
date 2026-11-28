"""Stockage objet protégé.

* ``EncryptedFilesystemStorage`` (défaut, développement et tests) : objets
  chiffrés au repos (Fernet, clé dérivée), noms opaques.
* ``S3Storage`` : MinIO/S3 via le SDK ``minio`` (Docker Compose), seau privé,
  objets également chiffrés côté application avant envoi.
L'accès aux contenus passe toujours par l'API (permissions + lien temporaire
signé) ; le stockage n'est jamais exposé directement.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Protocol

from horizon.core.config import get_settings
from horizon.core.crypto import fernet


class ObjectStorage(Protocol):
    name: str

    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...


class EncryptedFilesystemStorage:
    name = "filesystem-chiffré"

    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace("..", "_")
        return self.root / safe

    def put(self, key: str, data: bytes) -> None:
        p = self._path(key)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(fernet().encrypt(data))
        os.replace(tmp, p)

    def get(self, key: str) -> bytes:
        return fernet().decrypt(self._path(key).read_bytes())


class S3Storage:
    name = "s3-minio"

    def __init__(self):
        from minio import Minio

        st = get_settings()
        self.bucket = st.s3_bucket
        self.client = Minio(st.s3_endpoint, access_key=st.s3_access_key, secret_key=st.s3_secret_key, secure=st.s3_secure)
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put(self, key: str, data: bytes) -> None:
        enc = fernet().encrypt(data)
        self.client.put_object(self.bucket, key, io.BytesIO(enc), len(enc), content_type="application/octet-stream")

    def get(self, key: str) -> bytes:
        resp = self.client.get_object(self.bucket, key)
        try:
            return fernet().decrypt(resp.read())
        finally:
            resp.close()
            resp.release_conn()


_storage: ObjectStorage | None = None


def storage() -> ObjectStorage:
    global _storage
    if _storage is None:
        st = get_settings()
        _storage = S3Storage() if st.storage_backend == "s3" else EncryptedFilesystemStorage(st.storage_path)
    return _storage
