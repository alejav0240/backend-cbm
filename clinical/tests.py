import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from graphene_django.utils.testing import GraphQLTestCase
from config.schema import schema
from clinical.models import Patient, PatientClinicalNote

User = get_user_model()

class ClinicalMutationTests(GraphQLTestCase):
    GRAPHQL_SCHEMA = schema
    GRAPHQL_URL = "/graphql/"

    def setUp(self):
        # Creamos un terapeuta/admin
        self.author = User.objects.create_user(
            username="therapist", 
            email="t@cbm.com", 
            password="pass",
            ci="11111111"
        )

    def _execute_query(self, query, variables=None):
        response = self.query(query, variables=variables)
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            print(f"\nERROR: Status {response.status_code}: {response.content.decode('utf-8')}")
            raise

    def test_create_patient_creates_default_notes(self):
        """Prueba que al crear un paciente se generen sus notas clínicas base"""
        mutation = """
            mutation CreatePatient($authorId: ID!, $firstName: String!, $lastName: String!) {
                createPatient(authorId: $authorId, firstName: $firstName, lastName: $lastName) {
                    patient { id firstName }
                }
            }
        """
        variables = {
            "authorId": str(self.author.id),
            "firstName": "Juanito",
            "lastName": "Pérez"
        }
        response = self.query(mutation, variables=variables)
        self.assertResponseNoErrors(response)
        
        # Obtenemos el paciente de la DB directamente para evitar líos con Relay IDs
        patient = Patient.objects.get(first_name="Juanito", last_name="Pérez")
        
        # Verificar que se crearon exactamente 7 notas por defecto
        notes_count = PatientClinicalNote.objects.filter(patient_id=patient.id).count()
        self.assertEqual(notes_count, 7)

    def test_update_clinical_notes_is_idempotent(self):
        """Prueba que UpdateClinicalNotes actualiza en lugar de duplicar"""
        # 1. Crear paciente primero
        patient = Patient.objects.create(first_name="Leo", last_name="Messi")
        category = "PHYSICAL_AREA" # En DB será PHYSICAL_AREA (Mayúsculas)
        PatientClinicalNote.objects.create(
            patient=patient, 
            author=self.author, 
            category=category, 
            content="Inicial"
        )

        mutation = """
            mutation UpdateNotes($patientId: ID!, $authorId: ID!, $notes: [BasicNote]!) {
                updateClinicalNotes(patientId: $patientId, authorId: $authorId, notes: $notes) {
                    notesUpdated { category content }
                }
            }
        """
        # 2. Intentamos actualizar con minúsculas o mezcla
        variables = {
            "patientId": str(patient.id),
            "authorId": str(self.author.id),
            "notes": [
                {"category": "physical_area", "content": "Actualizado"}
            ]
        }
        
        response = self.query(mutation, variables=variables)
        self.assertResponseNoErrors(response)
        
        # 3. Verificar que NO hay duplicados y el contenido cambió
        note = PatientClinicalNote.objects.get(patient=patient, category=category)
        self.assertEqual(note.content, "Actualizado")
        self.assertEqual(PatientClinicalNote.objects.filter(patient=patient).count(), 1)
