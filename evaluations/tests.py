import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from graphene_django.utils.testing import GraphQLTestCase
from config.schema import schema
from clinical.models import Patient, PatientClinicalNote
from evaluations.models import (
    Scale,
    Subscale,
    ScaleEvaluation,
    Form,
    FormQuestion,
    FormAssignment,
    FormResponse,
)

User = get_user_model()

class EvaluationTests(GraphQLTestCase):
    GRAPHQL_SCHEMA = schema
    GRAPHQL_URL = "/graphql/"

    def setUp(self):
        self.therapist = User.objects.create_user(
            username="evaluator", 
            email="ev@cbm.com", 
            password="pass",
            ci="33333333"
        )
        self.therapist.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="evaluations",
            content_type__model="scaleevaluation",
            codename="add_scaleevaluation",
        ))
        self.therapist.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="evaluations",
            content_type__model="scale",
            codename__in=("add_scale", "view_scale"),
        ))
        self.therapist.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="evaluations",
            content_type__model="form",
            codename__in=("add_form", "view_form", "change_form", "delete_form"),
        ))
        self.therapist.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="clinical",
            content_type__model="patient",
            codename="delete_patient",
        ))
        self.client.force_login(self.therapist)
        self.patient = Patient.objects.create(first_name="Leo", last_name="Evaluated")
        PatientClinicalNote.objects.create(
            patient=self.patient,
            author=self.therapist,
            category=PatientClinicalNote.Category.GENERAL_OBJECTIVE,
            content="Inicial",
        )
        
        # Escala de prueba
        self.scale = Scale.objects.create(name="Test Scale", scale_type="subscale")
        self.subscale1 = Subscale.objects.create(scale=self.scale, name="S1", max_value=10)
        
        # Otra escala para pruebas de validación
        self.other_scale = Scale.objects.create(name="Other", scale_type="subscale")
        self.other_subscale = Subscale.objects.create(scale=self.other_scale, name="Other S1", max_value=5)

    def test_add_scale_response_valid(self):
        """Prueba guardar una evaluación con subescalas válidas"""
        mutation = """
            mutation AddScale($patientId: ID!, $evaluatorId: ID!, $scaleId: ID!, $subscales: [ResponseSubScale]) {
                addScaleResponse(patientId: $patientId, evaluatorId: $evaluatorId, scaleId: $scaleId, subscales: $subscales) {
                    success
                    message
                }
            }
        """
        variables = {
            "patientId": str(self.patient.id),
            "evaluatorId": str(self.therapist.id),
            "scaleId": str(self.scale.id),
            "subscales": [
                {"subscaleId": str(self.subscale1.id), "score": 8}
            ]
        }
        response = self.query(mutation, variables=variables)
        self.assertResponseNoErrors(response)
        
        content = json.loads(response.content)
        self.assertTrue(content["data"]["addScaleResponse"]["success"])
        
        # Verificar en DB
        eval_exists = ScaleEvaluation.objects.filter(patient=self.patient, scale=self.scale).exists()
        self.assertTrue(eval_exists)

    def test_add_scale_response_invalid_subscale(self):
        """Prueba que falle si la subescala no pertenece a la escala"""
        mutation = """
            mutation AddScale($patientId: ID!, $evaluatorId: ID!, $scaleId: ID!, $subscales: [ResponseSubScale]) {
                addScaleResponse(patientId: $patientId, evaluatorId: $evaluatorId, scaleId: $scaleId, subscales: $subscales) {
                    success
                    message
                }
            }
        """
        variables = {
            "patientId": str(self.patient.id),
            "evaluatorId": str(self.therapist.id),
            "scaleId": str(self.scale.id), # Escala A
            "subscales": [
                {"subscaleId": str(self.other_subscale.id), "score": 5} # Subescala de Escala B
            ]
        }
        response = self.query(mutation, variables=variables)
        self.assertResponseNoErrors(response)
        
        content = json.loads(response.content)
        self.assertFalse(content["data"]["addScaleResponse"]["success"])
        self.assertIn("no pertenece a la escala seleccionada", content["data"]["addScaleResponse"]["message"])

    def test_delete_patient_from_clinical(self):
        """Prueba que la mutación movida a clinical funcione correctamente"""
        mutation = """
            mutation DeletePatient($id: ID!) {
                deletePatient(id: $id) {
                    success
                }
            }
        """
        variables = {"id": str(self.patient.id)}
        response = self.query(mutation, variables=variables)
        self.assertResponseNoErrors(response)
        
        content = json.loads(response.content)
        self.assertTrue(content["data"]["deletePatient"]["success"])
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.status, Patient.Status.INACTIVE)

    def test_create_assign_and_submit_form(self):
        create_form = """
            mutation CreateForm($questions: [QuestionInput]!) {
                createForm(name: "Seguimiento", questions: $questions) {
                    form { id questions { id question } }
                }
            }
        """
        content = json.loads(self.query(
            create_form,
            variables={"questions": [{
                "question": "¿Cómo se siente?",
                "questionType": "text",
            }]},
        ).content)
        form_id = content["data"]["createForm"]["form"]["id"]
        question_id = content["data"]["createForm"]["form"]["questions"][0]["id"]

        assign_form = """
            mutation AssignForm($formId: ID!, $assignedById: ID!, $patientId: ID!) {
                assignForm(
                    formId: $formId,
                    assignedById: $assignedById,
                    patientId: $patientId
                ) { assignment { id } }
            }
        """
        content = json.loads(self.query(assign_form, variables={
            "formId": form_id,
            "assignedById": str(self.therapist.id),
            "patientId": str(self.patient.id),
        }).content)
        assignment_id = content["data"]["assignForm"]["assignment"]["id"]

        submit_form = """
            mutation SubmitForm($assignmentId: ID!, $responses: [ResponseInput]!) {
                submitFullForm(assignmentId: $assignmentId, responses: $responses) {
                    success
                    assignment { id }
                }
            }
        """
        response = self.query(submit_form, variables={
            "assignmentId": assignment_id,
            "responses": [{"questionId": question_id, "responseText": "Bien"}],
        })

        self.assertResponseNoErrors(response)
        self.assertTrue(json.loads(response.content)["data"]["submitFullForm"]["success"])
        self.assertTrue(FormResponse.objects.filter(response="Bien").exists())

    def test_scales_query_supports_search_and_pagination(self):
        query = """
            query {
                scales(search: "Test", page: 1, pageSize: 1) {
                    totalCount
                    totalPages
                    currentPage
                    results { name }
                }
            }
        """

        content = json.loads(self.query(query).content)
        scales = content["data"]["scales"]

        self.assertEqual(scales["totalCount"], 1)
        self.assertEqual(scales["currentPage"], 1)
        self.assertEqual(scales["results"][0]["name"], "Test Scale")

    def test_form_assignment_mutation_rejects_other_assigner(self):
        other = User.objects.create_user(
            username="other_form_owner",
            email="other.form@cbm.com",
            password="pass",
            ci="15151515",
        )
        form = Form.objects.create(name="Protected form")
        assignment = FormAssignment.objects.create(
            form=form,
            assigned_by=other,
            patient=self.patient,
        )
        mutation = """
            mutation UpdateAssignment($id: ID!, $patientId: ID!) {
                updateFormAssignment(id: $id, patientId: $patientId) {
                    assignment { id }
                }
            }
        """

        content = json.loads(self.query(mutation, variables={
            "id": str(assignment.id),
            "patientId": str(self.patient.id),
        }).content)

        self.assertEqual(content["errors"][0]["message"], "No autorizado.")
