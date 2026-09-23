import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone
from graphene_django.utils.testing import GraphQLTestCase
from config.schema import schema
from clinical.models import Patient, PatientClinicalNote
from therapeutic_sessions.models import Session

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
        self.author.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="clinical",
            content_type__model="patient",
            codename__in=("add_patient", "change_patient", "view_patient", "delete_patient"),
        ))
        self.client.force_login(self.author)

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

    def test_patients_query_filters_and_paginates(self):
        first = Patient.objects.create(first_name="Ana", last_name="Uno")
        second = Patient.objects.create(first_name="Ana", last_name="Dos")
        Patient.objects.create(
            first_name="Ana", last_name="Inactive", status=Patient.Status.INACTIVE
        )
        for number, patient in enumerate((first, second), start=1):
            Session.objects.create(
                patient=patient,
                therapist=self.author,
                session_date=timezone.now(),
                session_type="individual",
                session_number=number,
                cycle_number=1,
            )

        query = """
            query {
                patients(search: "Ana", page: 1, pageSize: 1) {
                    totalCount
                    totalPages
                    currentPage
                    results { firstName lastName }
                }
            }
        """

        content = self._execute_query(query)
        patients = content["data"]["patients"]

        self.assertEqual(patients["totalCount"], 2)
        self.assertEqual(patients["totalPages"], 2)
        self.assertEqual(patients["currentPage"], 1)
        self.assertEqual(len(patients["results"]), 1)

    def test_update_patient_status_and_fields(self):
        patient = Patient.objects.create(first_name="Ana", last_name="Update")
        PatientClinicalNote.objects.create(
            patient=patient,
            author=self.author,
            category=PatientClinicalNote.Category.GENERAL_OBJECTIVE,
            content="Inicial",
        )
        mutation = """
            mutation UpdatePatient($id: ID!, $diagnosis: String!, $complete: Boolean!) {
                updatePatient(
                    id: $id,
                    diagnosis: $diagnosis,
                    registrationComplete: $complete
                ) {
                    patient { diagnosis registrationComplete }
                }
            }
        """

        content = self._execute_query(mutation, variables={
            "id": str(patient.id),
            "diagnosis": "Ansiedad",
            "complete": True,
        })

        self.assertEqual(content["data"]["updatePatient"]["patient"]["diagnosis"], "Ansiedad")
        patient.refresh_from_db()
        self.assertTrue(patient.registration_complete)

    def test_patients_query_excludes_patients_assigned_to_other_therapists(self):
        own = Patient.objects.create(first_name="Own", last_name="Patient")
        other = Patient.objects.create(first_name="Other", last_name="Patient")
        therapist = User.objects.create_user(
            username="other_clinical_therapist",
            email="other.clinical@cbm.com",
            password="pass",
            ci="12121212",
        )
        Session.objects.create(
            patient=own,
            therapist=self.author,
            session_date=timezone.now(),
            session_type="individual",
        )
        Session.objects.create(
            patient=other,
            therapist=therapist,
            session_date=timezone.now(),
            session_type="individual",
        )

        content = self._execute_query("""
            query {
                patients(page: 1, pageSize: 10) {
                    totalCount
                    results { firstName }
                }
            }
        """)

        patients = content["data"]["patients"]
        self.assertEqual(patients["totalCount"], 1)
        self.assertEqual(patients["results"][0]["firstName"], "Own")

    def test_update_patient_rejects_patient_owned_by_other_therapist(self):
        other = User.objects.create_user(
            username="mutation_owner",
            email="mutation.owner@cbm.com",
            password="pass",
            ci="13131313",
        )
        patient = Patient.objects.create(first_name="Protected", last_name="Patient")
        PatientClinicalNote.objects.create(
            patient=patient,
            author=other,
            category=PatientClinicalNote.Category.GENERAL_OBJECTIVE,
            content="Owner note",
        )

        content = self._execute_query("""
            mutation UpdatePatient($id: ID!) {
                updatePatient(id: $id, diagnosis: "Forbidden") {
                    patient { diagnosis }
                }
            }
        """, variables={"id": str(patient.id)})

        self.assertEqual(content["errors"][0]["message"], "No autorizado.")
