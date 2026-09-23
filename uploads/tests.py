import json

from django.test import Client, TestCase, override_settings
from django.contrib.auth import get_user_model
from clinical.models import Patient
from therapeutic_sessions.models import Session


@override_settings(ONEDRIVE_SERVICE_KEY="test-service-key")
class UploadMutationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.therapist = get_user_model().objects.create_user(
            username="upload_therapist",
            email="upload@cbm.com",
            password="pass",
            ci="88888888",
        )
        self.session = Session.objects.create(
            patient=Patient.objects.create(first_name="Video", last_name="Patient"),
            therapist=self.therapist,
            session_type="individual",
            session_number=1,
            cycle_number=1,
        )

    def _post(self, query, variables=None, authorized=False):
        headers = {"HTTP_X_SERVICE_KEY": "test-service-key"} if authorized else {}
        return self.client.post(
            "/graphql/",
            data=json.dumps({"query": query, "variables": variables or {}}),
            content_type="application/json",
            **headers,
        )

    def test_upload_mutation_requires_service_key(self):
        response = self._post(
            """
            mutation Mark($sessionId: ID!) {
                marcarSubidaEnProgreso(sessionId: $sessionId) { success }
            }
            """,
            {"sessionId": str(self.session.id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["errors"][0]["message"], "No autorizado.")

    def test_upload_mutations_update_session_and_notify_therapist(self):
        response = self._post(
            """
            mutation Mark($sessionId: ID!) {
                marcarSubidaEnProgreso(sessionId: $sessionId) { success }
            }
            """,
            {"sessionId": str(self.session.id)},
            authorized=True,
        )
        self.assertIsNone(response.json().get("errors"))

        self.session.refresh_from_db()
        self.assertEqual(self.session.video_status, Session.VideoStatus.SUBIENDO)

        response = self._post(
            """
            mutation Complete($sessionId: ID!, $url: String!) {
                completarSubidaSesion(
                    sessionId: $sessionId,
                    videoUrl: $url,
                    storage: "local",
                    ok: true,
                    jobId: "job-1"
                ) { success }
            }
            """,
            {"sessionId": str(self.session.id), "url": "https://cdn.test/video.mp4"},
            authorized=True,
        )
        self.assertIsNone(response.json().get("errors"))

        self.session.refresh_from_db()
        self.assertEqual(self.session.video_status, Session.VideoStatus.SUBIDO)
        self.assertEqual(self.session.video_url, "https://cdn.test/video.mp4")
        notification = self.therapist.notifications.get()
        self.assertEqual(notification.tipo, "subida_exitosa")
