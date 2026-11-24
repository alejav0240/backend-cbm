import base64
import json
import os
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

CONTENT_TYPE = "application/vnd.cbm.encrypted+json"
ALGORITHM = "RSA-OAEP-256+A256GCM"
VERSION = 1
INVALID_ENCRYPTED_PAYLOAD = "Invalid encrypted payload"


def _b64decode(value):
    if not isinstance(value, str):
        raise ValueError(INVALID_ENCRYPTED_PAYLOAD)
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _b64encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _aad(request_path):
    return f"POST {request_path} v{VERSION}".encode("utf-8")


@lru_cache(maxsize=1)
def private_key():
    configured = os.getenv("APP_ENCRYPTION_PRIVATE_KEY_FILE", "")
    if not configured:
        raise RuntimeError("APP_ENCRYPTION_PRIVATE_KEY_FILE is required")
    path = configured if os.path.isabs(configured) else settings.BASE_DIR / configured
    with open(path, "rb") as key_file:
        return serialization.load_pem_private_key(key_file.read(), password=None)


def key_id():
    return os.getenv("APP_ENCRYPTION_KEY_ID", "app-key-v1")


def public_jwk():
    numbers = private_key().public_key().public_numbers()
    return {
        "kty": "RSA",
        "n": _b64encode(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
        "e": _b64encode(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
        "alg": "RSA-OAEP-256",
        "use": "enc",
        "kid": key_id(),
    }


def unwrap_aes_key(wrapped_key, wrapped_key_id):
    if wrapped_key_id != key_id():
        raise ValueError("Unsupported encryption key")
    return private_key().decrypt(
        _b64decode(wrapped_key),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )


def decrypt_envelope(envelope, request_path):
    if not isinstance(envelope, dict) or envelope.get("v") != VERSION:
        raise ValueError(INVALID_ENCRYPTED_PAYLOAD)
    if envelope.get("alg") != ALGORITHM or envelope.get("kid") != key_id():
        raise ValueError("Unsupported encryption key")
    aes_key = unwrap_aes_key(envelope["ek"], envelope["kid"])
    try:
        plaintext = AESGCM(aes_key).decrypt(
            _b64decode(envelope["iv"]),
            _b64decode(envelope["ct"]),
            _aad(request_path),
        )
    except (InvalidTag, ValueError) as exc:
        raise ValueError(INVALID_ENCRYPTED_PAYLOAD) from exc
    return plaintext, aes_key


def encrypt_payload(payload, aes_key, request_path):
    iv = os.urandom(12)
    ciphertext = AESGCM(aes_key).encrypt(iv, payload, _aad(request_path))
    return json.dumps(
        {"v": VERSION, "alg": "A256GCM", "kid": key_id(), "iv": _b64encode(iv), "ct": _b64encode(ciphertext)},
        separators=(",", ":"),
    ).encode("utf-8")
