import json

from django.test import Client, TestCase, override_settings

from clinical.models import Patient
from evaluations.models import Scale, ScaleEvaluation, Subscale
from therapeutic_sessions.models import Session
from users.models import User

from .models import ProcessingRun


@override_settings(ML_SERVICE_API_KEY="test-ml-key")
class DemucaPersistenceTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.therapist = User.objects.create_user(
            username="demuca_therapist",
            password="test-password",
            ci="77777777",
        )
        self.patient = Patient.objects.create(first_name="DEMUCA", last_name="Patient")
        self.session = Session.objects.create(
            patient=self.patient,
            therapist=self.therapist,
            session_type="individual",
            session_number=1,
        )
        self.scale = Scale.objects.create(
            name="Escala DEMUCA",
            scale_type=Scale.ScaleType.SUBSCALE,
        )
        Subscale.objects.create(
            scale=self.scale,
            name="Estereotipias",
            category="Comportamientos Restrictivos",
            max_value=2,
        )
        self.run = ProcessingRun.objects.create(
            session=self.session,
            requested_by=self.therapist,
        )

    def test_completed_callback_persists_demuca_in_existing_scale_tables(self):
        response = self.client.post(
            "/api/ml/processing-callback/",
            data=json.dumps(
                {
                    "run_id": self.run.external_run_id,
                    "status": "completed",
                    "result": {
                        "demuca": {
                            "comportamientos_restrictivos": {
                                "estereotipias": 2,
                            },
                        }
                    },
                }
            ),
            content_type="application/json",
            HTTP_X_ML_SERVICE_KEY="test-ml-key",
        )

        self.assertEqual(response.status_code, 200)
        evaluation = ScaleEvaluation.objects.get(
            session=self.session,
            scale=self.scale,
        )
        self.assertEqual(evaluation.patient_id, self.patient.pk)
        self.assertEqual(
            evaluation.subscale_responses.get(subscale__name="Estereotipias").score,
            2,
        )

        self.client.post(
            "/api/ml/processing-callback/",
            data=json.dumps(
                {
                    "run_id": self.run.external_run_id,
                    "status": "completed",
                    "result": {
                        "demuca": {
                            "comportamientos_restrictivos": {
                                "estereotipias": 1,
                            },
                        }
                    },
                }
            ),
            content_type="application/json",
            HTTP_X_ML_SERVICE_KEY="test-ml-key",
        )

        self.assertEqual(
            ScaleEvaluation.objects.filter(
                session=self.session,
                scale=self.scale,
            ).count(),
            1,
        )
        self.assertEqual(
            evaluation.subscale_responses.get(subscale__name="Estereotipias").score,
            2,
        )

    def test_worker_does_not_overwrite_existing_evaluation(self):
        self.client.post(
            "/api/ml/processing-callback/",
            data=json.dumps(
                {
                    "run_id": self.run.external_run_id,
                    "status": "completed",
                    "result": {
                        "demuca": {
                            "comportamientos_restrictivos": {
                                "estereotipias": 2,
                            },
                        }
                    },
                }
            ),
            content_type="application/json",
            HTTP_X_ML_SERVICE_KEY="test-ml-key",
        )
        evaluation = ScaleEvaluation.objects.get(session=self.session, scale=self.scale)
        response = evaluation.subscale_responses.get(subscale__name="Estereotipias")
        response.score = 1
        response.save(update_fields=["score"])

        self.client.post(
            "/api/ml/processing-callback/",
            data=json.dumps(
                {
                    "run_id": self.run.external_run_id,
                    "status": "completed",
                    "result": {
                        "demuca": {
                            "comportamientos_restrictivos": {
                                "estereotipias": 0,
                            },
                        }
                    },
                }
            ),
            content_type="application/json",
            HTTP_X_ML_SERVICE_KEY="test-ml-key",
        )

        response.refresh_from_db()
        self.assertEqual(response.score, 1)
