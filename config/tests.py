import json

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
