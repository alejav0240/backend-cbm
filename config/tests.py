import json
import os
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from config.middleware import ServiceKeyCSRFExemptMiddleware


@override_settings(ONEDRIVE_SERVICE_KEY="test-service-key")
class ServiceKeyCSRFExemptMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = ServiceKeyCSRFExemptMiddleware(lambda request: None)

    def _request(self, query, service_key="test-service-key", operation_name=None):
        return self.factory.post(
            "/graphql/",
            data=json.dumps({"query": query, "operationName": operation_name}),
            content_type="application/json",
            HTTP_X_SERVICE_KEY=service_key,
        )

    def test_service_key_only_bypasses_csrf_for_upload_operations(self):
        request = self._request(
            "mutation { marcarSubidaEnProgreso(sessionId: 1) { success } }"
        )

        self.middleware.process_request(request)

        self.assertTrue(request._dont_enforce_csrf_checks)

    @patch.dict(os.environ, {"MULTIMODAL_SERVICE_KEY": "pipeline-service-key"})
    def test_pipeline_service_key_bypasses_csrf_only_for_job_upload(self):
        request = self.factory.post(
            "/api/pipeline-multimodal/trabajos/",
            HTTP_X_SERVICE_KEY="pipeline-service-key",
        )

        self.middleware.process_request(request)

        self.assertTrue(request._dont_enforce_csrf_checks)

    @patch.dict(os.environ, {"MULTIMODAL_SERVICE_KEY": "pipeline-service-key"})
    def test_pipeline_without_service_key_keeps_csrf_protection(self):
        request = self.factory.post(
            "/api/pipeline-multimodal/trabajos/",
            HTTP_X_SERVICE_KEY="wrong-key",
        )

        self.middleware.process_request(request)

        self.assertFalse(hasattr(request, "_dont_enforce_csrf_checks"))

    @override_settings(ML_SERVICE_API_KEY="callback-service-key")
    def test_ml_callback_key_bypasses_csrf_for_callback_only(self):
        request = self.factory.post(
            "/api/ml/processing-callback/",
            HTTP_X_ML_SERVICE_KEY="callback-service-key",
        )

        response = self.middleware.process_request(request)

        self.assertIsNone(response)
        self.assertTrue(request._dont_enforce_csrf_checks)

    @override_settings(ML_SERVICE_API_KEY="callback-service-key")
    def test_ml_callback_without_valid_key_is_rejected(self):
        request = self.factory.post(
            "/api/ml/processing-callback/",
            HTTP_X_ML_SERVICE_KEY="wrong-key",
        )

        response = self.middleware.process_request(request)

        self.assertEqual(response.status_code, 401)
        self.assertFalse(hasattr(request, "_dont_enforce_csrf_checks"))

    def test_service_key_does_not_bypass_csrf_for_regular_graphql_operations(self):
        request = self._request("query { me { username } }")

        self.middleware.process_request(request)

        self.assertFalse(hasattr(request, "_dont_enforce_csrf_checks"))

    def test_operation_name_substrings_do_not_bypass_csrf(self):
        request = self._request("query marcarSubidaEnProgreso { me { username } }")

        self.middleware.process_request(request)

        self.assertFalse(hasattr(request, "_dont_enforce_csrf_checks"))

    def test_invalid_graphql_payload_does_not_raise_or_bypass_csrf(self):
        request = self._request(None)

        self.middleware.process_request(request)

        self.assertFalse(hasattr(request, "_dont_enforce_csrf_checks"))

    def test_only_selected_operation_can_bypass_csrf(self):
        request = self._request(
            """
            query Browser { me { username } }
            mutation Worker { marcarSubidaEnProgreso(sessionId: 1) { success } }
            """,
            operation_name="Browser",
        )

        self.middleware.process_request(request)

        self.assertFalse(hasattr(request, "_dont_enforce_csrf_checks"))
