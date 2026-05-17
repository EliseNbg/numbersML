"""AES-256-GCM encryption service for API secrets."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Raised when encryption or decryption fails."""


class EncryptionService:
    """AES-256-GCM encryption for API secrets.

    Uses the cryptography library for AES-256-GCM encryption.
    Master key must be provided via BINANCE_MASTER_KEY env var.

    Args:
        master_key: 32-byte master key (or hex string).

    Raises:
        EncryptionError: If master key is missing or invalid.

    Example:
        >>> service = EncryptionService()
        >>> encrypted = service.encrypt("my-secret-key")
        >>> decrypted = service.decrypt(encrypted)
    """

    def __init__(self, master_key: bytes | str | None = None) -> None:
        self._key = self._load_master_key(master_key)

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt string, return nonce + ciphertext + tag.

        Args:
            plaintext: String to encrypt.

        Returns:
            Encrypted bytes (nonce + ciphertext + tag).

        Raises:
            EncryptionError: If encryption fails.
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aesgcm = AESGCM(self._key)
        nonce = os.urandom(12)  # 96-bit nonce for GCM
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return nonce + ciphertext

    def decrypt(self, encrypted: bytes) -> str:
        """Decrypt and return original string.

        Args:
            encrypted: Encrypted bytes (nonce + ciphertext + tag).

        Returns:
            Decrypted plaintext string.

        Raises:
            EncryptionError: If decryption fails.
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        if len(encrypted) < 12:
            raise EncryptionError("Encrypted data too short")

        nonce = encrypted[:12]
        ciphertext = encrypted[12:]

        try:
            aesgcm = AESGCM(self._key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode("utf-8")
        except Exception as exc:
            raise EncryptionError(f"Decryption failed: {exc}") from exc

    @staticmethod
    def _load_master_key(master_key: bytes | str | None = None) -> bytes:
        """Load master key from parameter or environment variable.

        Args:
            master_key: Optional master key (bytes or hex string).

        Returns:
            32-byte master key.

        Raises:
            EncryptionError: If master key is missing or invalid.
        """
        key_value = master_key or os.environ.get("BINANCE_MASTER_KEY")

        if key_value is None:
            raise EncryptionError(
                "BINANCE_MASTER_KEY environment variable is required"
            )

        if isinstance(key_value, str):
            if len(key_value) == 64:
                return bytes.fromhex(key_value)
            if len(key_value) == 32:
                return key_value.encode("utf-8")
            raise EncryptionError(
                "Master key must be 32 bytes or 64 hex characters"
            )

        if len(key_value) != 32:
            raise EncryptionError("Master key must be exactly 32 bytes")

        return key_value
