import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from graphene_django.utils.testing import GraphQLTestCase
from config.schema import schema
from clinical.models import Patient
from evaluations.models import Scale, Subscale, ScaleEvaluation

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
        self.patient = Patient.objects.create(first_name="Leo", last_name="Evaluated")
        
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
        self.assertFalse(Patient.objects.filter(id=self.patient.id).exists())
