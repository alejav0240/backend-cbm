import json
import os
import tempfile
from pathlib import Path

GRAPHQL_PATH = '/graphql/'

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from config.application_encryption import (
    CONTENT_TYPE,
    _aad,
    _b64decode,
    _b64encode,
    decrypt_envelope,
    encrypt_payload,
    private_key,
)
from config.encryption_middleware import ApplicationEncryptionMiddleware


class ApplicationEncryptionTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.key_path = Path(cls.temp_dir.name) / "private.pem"
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        cls.previous_key_path = os.environ.get("APP_ENCRYPTION_PRIVATE_KEY_FILE")
        os.environ["APP_ENCRYPTION_PRIVATE_KEY_FILE"] = str(cls.key_path)
        private_key.cache_clear()

    @classmethod
    def tearDownClass(cls):
        private_key.cache_clear()
        if cls.previous_key_path is None:
            os.environ.pop("APP_ENCRYPTION_PRIVATE_KEY_FILE", None)
        else:
            os.environ["APP_ENCRYPTION_PRIVATE_KEY_FILE"] = cls.previous_key_path
        cls.temp_dir.cleanup()
        super().tearDownClass()

    def _request_envelope(self, path, body):
        aes_key = os.urandom(32)
        iv = os.urandom(12)
        ciphertext = AESGCM(aes_key).encrypt(iv, body, _aad(path))
        wrapped_key = private_key().public_key().encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return {
            "v": 1,
            "alg": "RSA-OAEP-256+A256GCM",
            "kid": "app-key-v1",
            "iv": _b64encode(iv),
            "ek": _b64encode(wrapped_key),
            "ct": _b64encode(ciphertext),
        }, aes_key

    @override_settings(APP_ENCRYPTION_ENABLED=True)
    def test_request_and_response_round_trip(self):
        request_envelope, aes_key = self._request_envelope(
            GRAPHQL_PATH, b'{"query":"{ me { username } }"}'
        )
        request = RequestFactory().post(
            GRAPHQL_PATH,
            data=json.dumps(request_envelope),
            content_type=CONTENT_TYPE,
        )
        middleware = ApplicationEncryptionMiddleware(
            lambda current_request: JsonResponse({"ok": True})
        )

        response = middleware(request)

        self.assertEqual(response["Content-Type"], CONTENT_TYPE)
        response_envelope = json.loads(response.content)
        response_payload = AESGCM(aes_key).decrypt(
            _b64decode(response_envelope["iv"]),
            _b64decode(response_envelope["ct"]),
            _aad(GRAPHQL_PATH),
        )
        self.assertEqual(json.loads(response_payload), {"ok": True})

    def test_request_path_is_authenticated(self):
        envelope, _ = self._request_envelope(GRAPHQL_PATH, b"{}")

        with self.assertRaises(ValueError):
            decrypt_envelope(envelope, "/api/other/")

    @override_settings(APP_ENCRYPTION_ENABLED=False)
    def test_middleware_passes_plaintext_when_disabled(self):
        request = RequestFactory().post(
            GRAPHQL_PATH, data=json.dumps({"query": "{}"}), content_type="application/json"
        )
        middleware = ApplicationEncryptionMiddleware(
            lambda current_request: JsonResponse({"ok": True})
        )

        response = middleware(request)

        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(json.loads(response.content), {"ok": True})

    @override_settings(APP_ENCRYPTION_ENABLED=False)
    def test_disabled_middleware_does_not_require_response_key(self):
        request = RequestFactory().get(
            GRAPHQL_PATH,
            HTTP_X_CBM_ENCRYPTED_RESPONSE="1",
            HTTP_X_CBM_RESPONSE_KEY="invalid",
            HTTP_X_CBM_RESPONSE_KEY_ID="invalid",
        )
        middleware = ApplicationEncryptionMiddleware(
            lambda current_request: JsonResponse({"ok": True})
        )

        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"ok": True})
