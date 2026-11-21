"""Column-level encryption (AES-256-GCM) for secrets such as TOTP keys and OAuth tokens."""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_BYTES = 12


class Encryptor:
    def __init__(self, key_b64: str) -> None:
        key = base64.b64decode(key_b64)
        if len(key) != 32:
            raise ValueError("NEXUS_ENCRYPTION_KEY must be base64 of exactly 32 bytes")
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: str, associated_data: bytes = b"") -> bytes:
        nonce = os.urandom(_NONCE_BYTES)
        return nonce + self._aead.encrypt(nonce, plaintext.encode(), associated_data)

    def decrypt(self, blob: bytes, associated_data: bytes = b"") -> str:
        nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
        return self._aead.decrypt(nonce, ciphertext, associated_data).decode()
