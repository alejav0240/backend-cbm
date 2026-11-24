import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from graphql import GraphQLError

from clinical.models import Patient
from evaluations.models import Scale, ScaleEvaluation, Subscale
from therapeutic_sessions.models import Session
from users.models import User

from .annotation_models import AnnotationCase
from .models import ProcessingRun
from .mutations import (
    UpdateProcessingRun,
    _dispatch_to_ml,
    _get_session,
    _service_authorized,
)
from .pipeline.stages import (
    initial_pipeline_stages,
    normalize_pipeline_stages,
    result_semantic_status,
)


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

    def test_short_session_callback_uses_friendly_error_code(self):
        response = self.client.post(
            "/api/ml/processing-callback/",
            data=json.dumps(
                {
                    "run_id": self.run.external_run_id,
                    "status": "failed",
                    "error": {
                        "code": "ValueError",
                        "message": "window_index_validation_failed:windows_missing_or_empty",
                    },
                    "pipeline_stages": [
                        {
                            "id": "segmentation",
                            "status": "blocked",
                            "progress": 0,
                            "message": "window_index_validation_failed:windows_missing_or_empty",
                        }
                    ],
                }
            ),
            content_type="application/json",
            HTTP_X_ML_SERVICE_KEY="test-ml-key",
        )

        self.assertEqual(response.status_code, 200)
        self.run.refresh_from_db()
        self.assertEqual(self.run.error_code, "insufficient_duration_for_window")
        self.assertIn("demasiado corta", self.run.error_message)
        self.assertEqual(
            next(
                stage
                for stage in self.run.result_json["pipeline_stages"]
                if stage["id"] == "segmentation"
            )["status"],
            "blocked",
        )

    def test_callback_rejects_invalid_requests(self):
        cases = (
            (Client().post(
                "/api/ml/processing-callback/",
                data="{",
                content_type="application/json",
                HTTP_X_ML_SERVICE_KEY="test-ml-key",
            ), 400, "invalid_json"),
            (self.client.post(
                "/api/ml/processing-callback/",
                data=json.dumps({}),
                content_type="application/json",
                HTTP_X_ML_SERVICE_KEY="test-ml-key",
            ), 400, "run_id_required"),
            (self.client.post(
                "/api/ml/processing-callback/",
                data=json.dumps({"run_id": "missing", "status": "queued"}),
                content_type="application/json",
                HTTP_X_ML_SERVICE_KEY="test-ml-key",
            ), 404, "processing_run_not_found"),
            (self.client.post(
                "/api/ml/processing-callback/",
                data=json.dumps({"run_id": self.run.external_run_id, "status": "unknown"}),
                content_type="application/json",
                HTTP_X_ML_SERVICE_KEY="test-ml-key",
            ), 400, "invalid_status"),
        )
        for response, status, error in cases:
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.json()["error"], error)

        response = self.client.post(
            "/api/ml/processing-callback/",
            data=json.dumps({"run_id": self.run.external_run_id, "status": "completed"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_callback_persists_run_state_artifacts_and_annotation_cases(self):
        response = self.client.post(
            "/api/ml/processing-callback/",
            data=json.dumps(
                {
                    "run_id": self.run.external_run_id,
                    "status": "running",
                    "semantic_status": "authorized_model",
                    "result": {
                        "source_sha256": "a" * 64,
                        "artifacts": {
                            "video": "https://example.com/video.mp4",
                            "audio": {"path": "https://example.com/audio.wav", "sha256": "b" * 64},
                            "nested": {"uri": {"path": "https://example.com/nested"}},
                            "invalid": None,
                        },
                    },
                }
            ),
            content_type="application/json",
            HTTP_X_ML_SERVICE_KEY="test-ml-key",
        )
        self.assertEqual(response.status_code, 200)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, ProcessingRun.Status.RUNNING)
        self.assertEqual(self.run.source_sha256, "a" * 64)
        self.assertEqual(self.run.artifacts.count(), 3)
        self.assertEqual(self.run.artifacts.get(kind="audio").sha256, "b" * 64)

        response = self.client.post(
            "/api/ml/processing-callback/",
            data=json.dumps(
                {
                    "run_id": self.run.external_run_id,
                    "status": "completed",
                    "result": {
                        "review_required": True,
                        "model_predictions": {
                            "windows": [
                                {
                                    "window_id": "w-1",
                                    "start_seconds": 1,
                                    "end_seconds": 2,
                                    "predictions": {
                                        "audio__speech": True,
                                        "pose__standing": False,
                                        3: True,
                                    },
                                },
                                {"window_id": "", "predictions": {"audio__skip": True}},
                                {"window_id": "bad", "predictions": "invalid"},
                                {"window_id": "bad-time", "start_seconds": "x", "end_seconds": 2},
                            ]
                        },
                    },
                }
            ),
            content_type="application/json",
            HTTP_X_ML_SERVICE_KEY="test-ml-key",
        )
        self.assertEqual(response.status_code, 200)
        labels = set(
            AnnotationCase.objects.filter(run=self.run).values_list("label", flat=True)
        )
        self.assertEqual(labels, {"audio__speech", "3"})
        self.assertTrue(
            all(
                case.source == "provisional"
                for case in AnnotationCase.objects.filter(run=self.run)
            )
        )

    def test_pipeline_stage_normalization_and_semantic_status(self):
        self.assertEqual(len(initial_pipeline_stages()), 9)
        stages = normalize_pipeline_stages(
            [
                {"key": "segmentation", "status": "invalid", "progress": "150", "artifacts": [1]},
                {"id": "pose", "progress": "not-a-number"},
                {"id": "unknown"},
                "invalid",
            ]
        )
        segmentation = next(stage for stage in stages if stage["id"] == "segmentation")
        self.assertEqual(segmentation["status"], "pending")
        self.assertEqual(segmentation["progress"], 100)
        self.assertEqual(segmentation["artifact_kinds"], ["1"])
        self.assertEqual(normalize_pipeline_stages(None)[0]["status"], "pending")
        self.assertEqual(result_semantic_status(None), "pending")
        self.assertEqual(
            result_semantic_status({"model_predictions": {"status": "unavailable"}}),
            "provisional_evidence",
        )
        self.assertEqual(
            result_semantic_status({"demuca": {"review_required": True}}),
            "provisional_evidence",
        )

    def test_update_processing_run_mutation_normalizes_result_and_artifacts(self):
        info = SimpleNamespace(
            context=SimpleNamespace(
                headers={"X-ML-Service-Key": "test-ml-key"},
                user=self.therapist,
            )
        )
        result = {"status": "completed", "model_predictions": {"status": "unavailable"}}
        updated = UpdateProcessingRun.mutate(
            None,
            info,
            external_run_id=self.run.external_run_id,
            status="completed",
            result=result,
            source_sha256="c" * 64,
            error_code="worker_error",
            error_message="Worker failed",
            artifacts=[
                {"kind": "report", "uri": "https://example.com/report.json"},
                {"kind": "invalid"},
            ],
        )
        self.assertEqual(updated.processing_run.status, ProcessingRun.Status.COMPLETED)
        self.run.refresh_from_db()
        self.assertEqual(self.run.result_json["semantic_status"], "provisional_evidence")
        self.assertEqual(self.run.artifacts.get(kind="report").sha256, "")
        self.assertEqual(self.run.error_code, "worker_error")

        with self.assertRaises(GraphQLError):
            UpdateProcessingRun.mutate(
                None,
                SimpleNamespace(context=SimpleNamespace(headers={}, user=self.therapist)),
                external_run_id=self.run.external_run_id,
                status="completed",
            )
        with self.assertRaises(GraphQLError):
            UpdateProcessingRun.mutate(
                None,
                info,
                external_run_id=self.run.external_run_id,
                status="invalid",
            )

    def test_processing_mutation_helpers_cover_authorization_and_dispatch_fallback(self):
        staff_info = SimpleNamespace(
            context=SimpleNamespace(user=self.therapist, headers={"X-ML-Service-Key": "test-ml-key"})
        )
        self.therapist.is_staff = True
        self.assertEqual(_get_session(staff_info, str(self.session.pk)).pk, self.session.pk)
        with self.assertRaises(GraphQLError):
            _get_session(staff_info, "not-an-id")
        self.therapist.is_staff = False
        staff_info.context.user = User.objects.create_user(
            username="analysis_outsider",
            email="analysis.outsider@example.com",
            password="test-password",
            ci="88888888",
        )
        with self.assertRaises(GraphQLError):
            _get_session(staff_info, str(self.session.pk))
        self.assertTrue(_service_authorized(staff_info))
        self.assertFalse(
            _service_authorized(
                SimpleNamespace(context=SimpleNamespace(headers={}, user=self.therapist))
            )
        )

        with patch.dict(os.environ, {"ML_ORCHESTRATOR_URL": ""}):
            _dispatch_to_ml(self.run)
        self.run.refresh_from_db()
        self.assertEqual(self.run.error_code, "ml_dispatch_not_configured")
        self.assertEqual(self.run.status, ProcessingRun.Status.FAILED)

    def test_processing_run_type_resolvers_cover_review_and_metadata_paths(self):
        from .type import ProcessingRunType

        self.run.result_json = {
            "pipeline_stages": [
                {"id": "human_review", "status": "running", "progress": 50}
            ],
            "demuca": {"review_required": True},
        }
        self.run.metadata_json = {"source": "test"}
        self.run.save(update_fields=["result_json", "metadata_json"])
        self.assertEqual(ProcessingRunType.resolve_result(self.run, None), self.run.result_json)
        self.assertEqual(ProcessingRunType.resolve_metadata(self.run, None), {"source": "test"})
        self.assertTrue(ProcessingRunType.resolve_review_required(self.run, None))
        self.assertEqual(
            ProcessingRunType.resolve_semantic_status(self.run, None),
            "provisional_evidence",
        )
        self.assertEqual(
            ProcessingRunType.resolve_pipeline_stages(self.run, None)[0]["status"],
            "running",
        )

        from evaluations.models import ScaleEvaluation

        evaluation = ScaleEvaluation.objects.create(
            patient=self.patient,
            evaluator=self.therapist,
            scale=self.scale,
            session=self.session,
            review_status="accepted",
            reviewed_at=datetime.now(timezone.utc),
        )
        stages = ProcessingRunType.resolve_pipeline_stages(self.run, None)
        self.assertEqual(stages[0]["status"], "completed")
        self.assertFalse(ProcessingRunType.resolve_review_required(self.run, None))
        self.assertIsNotNone(evaluation.pk)
