"""Unit tests for EncryptionService."""
import os
from unittest.mock import patch

import pytest

from src.infrastructure.security.encryption import EncryptionError, EncryptionService


class TestEncryptDecryptRoundtrip:
    """Tests for encrypt/decrypt roundtrip."""

    def test_encrypt_decrypt_roundtrip(self) -> None:
        master_key = os.urandom(32)
        service = EncryptionService(master_key=master_key)
        plaintext = "my-secret-api-key"
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)
        assert decrypted == plaintext

    def test_different_encryption_produces_different_ciphertext(self) -> None:
        master_key = os.urandom(32)
        service = EncryptionService(master_key=master_key)
        plaintext = "same-secret"
        encrypted1 = service.encrypt(plaintext)
        encrypted2 = service.encrypt(plaintext)
        assert encrypted1 != encrypted2

    def test_encrypt_empty_string(self) -> None:
        master_key = os.urandom(32)
        service = EncryptionService(master_key=master_key)
        encrypted = service.encrypt("")
        decrypted = service.decrypt(encrypted)
        assert decrypted == ""

    def test_encrypt_unicode_string(self) -> None:
        master_key = os.urandom(32)
        service = EncryptionService(master_key=master_key)
        plaintext = "密钥测试"
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)
        assert decrypted == plaintext


class TestMasterKeyLoading:
    """Tests for master key loading."""

    def test_master_key_from_bytes(self) -> None:
        key = os.urandom(32)
        service = EncryptionService(master_key=key)
        encrypted = service.encrypt("test")
        assert service.decrypt(encrypted) == "test"

    def test_master_key_from_hex_string(self) -> None:
        key_hex = os.urandom(32).hex()
        service = EncryptionService(master_key=key_hex)
        encrypted = service.encrypt("test")
        assert service.decrypt(encrypted) == "test"

    def test_master_key_from_env_var(self) -> None:
        key_hex = os.urandom(32).hex()
        with patch.dict(os.environ, {"BINANCE_MASTER_KEY": key_hex}):
            service = EncryptionService()
            encrypted = service.encrypt("test")
            assert service.decrypt(encrypted) == "test"

    def test_master_key_missing_raises(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(EncryptionError, match="BINANCE_MASTER_KEY"):
                EncryptionService()

    def test_invalid_key_length_raises(self) -> None:
        with pytest.raises(EncryptionError, match="32 bytes"):
            EncryptionService(master_key=b"too-short")

    def test_invalid_hex_length_raises(self) -> None:
        with pytest.raises(EncryptionError, match="32 bytes"):
            EncryptionService(master_key="not-valid-hex")


class TestDecryptionErrors:
    """Tests for decryption error handling."""

    def test_decrypt_tampered_data_raises(self) -> None:
        master_key = os.urandom(32)
        service = EncryptionService(master_key=master_key)
        encrypted = service.encrypt("test")
        tampered = encrypted[:-1] + bytes([encrypted[-1] ^ 0xFF])
        with pytest.raises(EncryptionError, match="Decryption failed"):
            service.decrypt(tampered)

    def test_decrypt_too_short_raises(self) -> None:
        master_key = os.urandom(32)
        service = EncryptionService(master_key=master_key)
        with pytest.raises(EncryptionError, match="too short"):
            service.decrypt(b"short")

    def test_decrypt_wrong_key_raises(self) -> None:
        key1 = os.urandom(32)
        key2 = os.urandom(32)
        service1 = EncryptionService(master_key=key1)
        service2 = EncryptionService(master_key=key2)
        encrypted = service1.encrypt("test")
        with pytest.raises(EncryptionError, match="Decryption failed"):
            service2.decrypt(encrypted)


class TestSecurityRules:
    """Tests for security rules."""

    def test_api_key_not_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        master_key = os.urandom(32)
        service = EncryptionService(master_key=master_key)
        secret = "super-secret-key-12345"
        encrypted = service.encrypt(secret)

        # Ensure the secret is not in the encrypted output as plaintext
        assert secret not in str(encrypted)
        assert secret not in caplog.text
