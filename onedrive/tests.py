import json

from django.test import Client, TestCase, override_settings

from onedrive.models import OneDriveConnection


@override_settings(ONEDRIVE_SERVICE_KEY="test-service-key")
class OneDriveViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_token_endpoint_requires_service_key(self):
        response = self.client.get("/api/onedrive/token")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "No autorizado.")

    def test_token_endpoint_encrypts_and_returns_refresh_token(self):
        response = self.client.post(
            "/api/onedrive/token",
            data=json.dumps({
                "refresh_token": "refresh-secret",
                "user_email": "drive@cbm.com",
            }),
            content_type="application/json",
            HTTP_X_SERVICE_KEY="test-service-key",
        )

        self.assertEqual(response.status_code, 200)
        connection = OneDriveConnection.objects.get()
        self.assertNotEqual(connection.refresh_token_encrypted, "refresh-secret")

        response = self.client.get(
            "/api/onedrive/token",
            HTTP_X_SERVICE_KEY="test-service-key",
        )
        self.assertEqual(response.json()["refresh_token"], "refresh-secret")

    def test_status_is_public_and_reports_connection(self):
        response = self.client.get("/api/onedrive/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"connected": False})
