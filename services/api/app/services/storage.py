"""File storage. Local disk for now; the S3/MinIO backend arrives with documents
in phase 4. Keys are random, never derived from the user's file name."""

import hashlib
import secrets
from pathlib import Path

from app.core.config import get_settings

ALLOWED_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
}


class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("bad storage key")
        return path

    def put(self, user_id: str, data: bytes) -> tuple[str, str]:
        key = f"{user_id}/{secrets.token_hex(16)}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key, hashlib.sha256(data).hexdigest()

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


def get_storage() -> LocalStorage:
    return LocalStorage(get_settings().storage_dir)
