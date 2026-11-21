"""Encrypted columns for money and health values (AES-256-GCM, key from NEXUS_ENCRYPTION_KEY).

Values are stored as ciphertext bound to their table and column, so a value copied into
another column won't decrypt. Sums and trends are computed in Python after decrypting."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Any

from sqlalchemy import LargeBinary
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings
from app.core.crypto import Encryptor


@lru_cache(maxsize=4)
def _enc(key: str) -> Encryptor:
    return Encryptor(key)


def encryptor() -> Encryptor:
    return _enc(get_settings().encryption_key.get_secret_value())


class EncryptedText(TypeDecorator[str]):
    impl = LargeBinary
    cache_ok = True

    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label.encode()

    def process_bind_param(self, value: str | None, dialect: Dialect) -> bytes | None:
        return None if value is None else encryptor().encrypt(value, self.label)

    def process_result_value(self, value: Any, dialect: Dialect) -> str | None:
        return None if value is None else encryptor().decrypt(bytes(value), self.label)


class EncryptedDecimal(TypeDecorator[Decimal]):
    impl = LargeBinary
    cache_ok = True

    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label.encode()

    def process_bind_param(
        self, value: Decimal | float | int | None, dialect: Dialect
    ) -> bytes | None:
        return None if value is None else encryptor().encrypt(str(Decimal(str(value))), self.label)

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        return None if value is None else Decimal(encryptor().decrypt(bytes(value), self.label))
