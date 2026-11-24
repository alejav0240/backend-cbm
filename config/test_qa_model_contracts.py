from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase

from clinical.models import PatientClinicalNote, PlanStep
from evaluations.models import ScaleEvaluationSubscaleResponse
from onedrive.models import OneDriveConnection
from pipeline_multimodal.models import TherapistDatasetSample, TrabajoAnalisis
from therapeutic_sessions.models import SessionInventory, SessionResource
from users.models import OnboardingView, User


class ModelContractTests(SimpleTestCase):
    def test_user_identity_fields_are_unique_and_required(self):
        self.assertTrue(User._meta.get_field("ci").unique)
        self.assertTrue(User._meta.get_field("email").unique)
        self.assertFalse(User._meta.get_field("username").blank)

    def test_foreign_keys_keep_expected_delete_policies(self):
        self.assertEqual(
            PatientClinicalNote._meta.get_field("patient").remote_field.on_delete.__name__,
            "CASCADE",
        )
        self.assertEqual(
            SessionResource._meta.get_field("resource").remote_field.on_delete.__name__,
            "PROTECT",
        )
        self.assertEqual(
            SessionInventory._meta.get_field("item").remote_field.on_delete.__name__,
            "PROTECT",
        )

    def test_unique_constraints_cover_relationships_and_active_jobs(self):
        self.assertIn(
            ("session", "resource"),
            SessionResource._meta.unique_together,
        )
        self.assertIn(
            ("session", "item"),
            SessionInventory._meta.unique_together,
        )
        self.assertTrue(
            any(
                constraint.name == "pipeline_active_session_unique"
                for constraint in TrabajoAnalisis._meta.constraints
            )
        )
        self.assertTrue(
            any(
                constraint.name == "dataset_sample_session_window_unique"
                for constraint in TherapistDatasetSample._meta.constraints
            )
        )

    def test_custom_model_behaviors_are_present(self):
        self.assertTrue(hasattr(OneDriveConnection, "save_refresh_token"))
        self.assertTrue(hasattr(OneDriveConnection, "get_active"))
        self.assertTrue(hasattr(PlanStep, "save"))
        self.assertTrue(hasattr(ScaleEvaluationSubscaleResponse, "score"))


class ModelValidationTests(TestCase):
    def test_user_requires_unique_ci_and_email_at_database_boundary(self):
        User.objects.create_user(
            username="qa-user-1",
            email="qa@example.com",
            password="safe-password",
            ci="QA-001",
        )
        duplicate_ci = User(
            username="qa-user-2",
            email="other@example.com",
            password="safe-password",
            ci="QA-001",
        )
        with self.assertRaises(ValidationError):
            duplicate_ci.validate_unique()

    def test_onboarding_view_is_unique_per_user_and_view(self):
        user = User.objects.create_user(
            username="qa-onboarding",
            email="onboarding@example.com",
            password="safe-password",
            ci="QA-002",
        )
        OnboardingView.objects.create(user=user, view_key="/dashboard")
        duplicate = OnboardingView(user=user, view_key="/dashboard")
        with self.assertRaises(IntegrityError):
            duplicate.save()
