"""
Unit tests for WebhookSecurityService: authenticated encryption, HMAC-SHA256 signing, and key rotation.
Runs in any environment without external services.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.services.webhook_security import (
    WebhookSecurityService,
    WebhookSecurityError,
    WebhookKeyConfigurationError,
    WebhookDecryptionError,
)


@pytest.mark.unit
def test_generate_secret():
    service = WebhookSecurityService(encryption_key=Fernet.generate_key().decode())
    secret = service.generate_secret(32)
    assert isinstance(secret, str)
    assert len(secret) == 64  # 32 bytes in hex = 64 characters
    # Consecutive secrets should be unique
    assert secret != service.generate_secret(32)


@pytest.mark.unit
def test_encrypt_and_decrypt_round_trip(test_fernet_key: str):
    service = WebhookSecurityService(encryption_key=test_fernet_key)
    original_secret = "whsec_0123456789abcdef0123456789abcdef"

    encrypted = service.encrypt_secret(original_secret)
    assert isinstance(encrypted, str)
    assert encrypted != original_secret
    assert "whsec_" not in encrypted  # Plaintext is not visible in ciphertext

    decrypted = service.decrypt_secret(encrypted)
    assert decrypted == original_secret


@pytest.mark.unit
def test_fernet_randomized_ciphertext(test_fernet_key: str):
    service = WebhookSecurityService(encryption_key=test_fernet_key)
    secret = "shared-webhook-signing-secret"

    # Fernet includes an initialization vector and timestamp; ciphertexts differ
    c1 = service.encrypt_secret(secret)
    c2 = service.encrypt_secret(secret)
    assert c1 != c2
    assert service.decrypt_secret(c1) == secret
    assert service.decrypt_secret(c2) == secret


@pytest.mark.unit
def test_decrypt_with_tampered_ciphertext_fails(test_fernet_key: str):
    service = WebhookSecurityService(encryption_key=test_fernet_key)
    encrypted = service.encrypt_secret("valid_secret")

    # Tamper with the base64 ciphertext
    tampered = encrypted[:-5] + "AAAAA"
    with pytest.raises(WebhookDecryptionError):
        service.decrypt_secret(tampered)


@pytest.mark.unit
def test_decrypt_with_wrong_key_fails(test_fernet_key: str):
    service1 = WebhookSecurityService(encryption_key=test_fernet_key)
    encrypted = service1.encrypt_secret("valid_secret")

    # Different key
    other_key = Fernet.generate_key().decode()
    service2 = WebhookSecurityService(encryption_key=other_key)

    with pytest.raises(WebhookDecryptionError):
        service2.decrypt_secret(encrypted)


@pytest.mark.unit
def test_multi_key_rotation():
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()

    # Step 1: Secret was encrypted under old key
    old_service = WebhookSecurityService(encryption_key=old_key)
    original_secret = "secret-encrypted-under-old-key"
    ciphertext = old_service.encrypt_secret(original_secret)

    # Step 2: Service configured with key rotation ring [new_key, old_key]
    rotation_key_ring = f"{new_key},{old_key}"
    rotation_service = WebhookSecurityService(encryption_key=rotation_key_ring)

    # Can decrypt ciphertext produced by the old key
    decrypted = rotation_service.decrypt_secret(ciphertext)
    assert decrypted == original_secret

    # New encryptions use the primary (new) key
    new_ciphertext = rotation_service.encrypt_secret(original_secret)
    new_primary_service = WebhookSecurityService(encryption_key=new_key)
    assert new_primary_service.decrypt_secret(new_ciphertext) == original_secret


@pytest.mark.unit
def test_missing_or_empty_key_fails():
    service = WebhookSecurityService(encryption_key="")
    with pytest.raises(WebhookKeyConfigurationError):
        service.encrypt_secret("test")


@pytest.mark.unit
def test_sign_payload_and_verify():
    service = WebhookSecurityService(encryption_key=Fernet.generate_key().decode())
    secret = "my-webhook-secret-token"
    payload = b'{"event":"post.created","post_id":"123"}'

    signature = service.sign_payload(payload, secret)
    assert signature.startswith("sha256=")

    # Verification succeeds with matching signature
    assert service.verify_signature(payload, secret, signature) is True
    # Verification also accepts bare hex signature
    bare_signature = signature.removeprefix("sha256=")
    assert service.verify_signature(payload, secret, bare_signature) is True


@pytest.mark.unit
def test_verify_fails_with_altered_payload():
    service = WebhookSecurityService(encryption_key=Fernet.generate_key().decode())
    secret = "my-webhook-secret-token"
    payload = b'{"event":"post.created","amount":100}'
    tampered = b'{"event":"post.created","amount":999}'

    signature = service.sign_payload(payload, secret)
    assert service.verify_signature(tampered, secret, signature) is False


@pytest.mark.unit
def test_verify_fails_with_wrong_secret():
    service = WebhookSecurityService(encryption_key=Fernet.generate_key().decode())
    payload = b'{"event":"test"}'
    signature = service.sign_payload(payload, "secret-one")

    assert service.verify_signature(payload, "secret-two", signature) is False
