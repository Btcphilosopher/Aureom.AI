"""Encrypted, local-first storage for spatial data (maps, anchors, memory snapshots)."""

from __future__ import annotations

import json
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class EncryptedStorage:
    """
    Symmetric-encrypted key/value storage on local disk. Every record is
    written as its own encrypted file under ``directory`` -- nothing leaves
    the device unless an application explicitly exports it.
    """

    def __init__(self, directory: str | Path, key: bytes | None = None) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._key_path = self.directory / ".key"
        self.key = key or self._load_or_create_key()
        self._fernet = Fernet(self.key)

    def _load_or_create_key(self) -> bytes:
        if self._key_path.exists():
            return self._key_path.read_bytes()
        key = Fernet.generate_key()
        self._key_path.write_bytes(key)
        return key

    def _path_for(self, name: str) -> Path:
        safe_name = name.replace("/", "_")
        return self.directory / f"{safe_name}.enc"

    def save(self, name: str, data: dict) -> None:
        payload = json.dumps(data).encode("utf-8")
        token = self._fernet.encrypt(payload)
        self._path_for(name).write_bytes(token)

    def load(self, name: str) -> dict | None:
        path = self._path_for(name)
        if not path.exists():
            return None
        try:
            payload = self._fernet.decrypt(path.read_bytes())
        except InvalidToken as exc:
            raise ValueError(f"cannot decrypt {name!r}: wrong key or corrupted data") from exc
        return json.loads(payload.decode("utf-8"))

    def delete(self, name: str) -> None:
        path = self._path_for(name)
        if path.exists():
            path.unlink()

    def list_keys(self) -> list[str]:
        return [p.stem for p in self.directory.glob("*.enc")]

    def exists(self, name: str) -> bool:
        return self._path_for(name).exists()
