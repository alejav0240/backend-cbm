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

class SessionMutationTests(GraphQLTestCase):
    GRAPHQL_SCHEMA = schema
    GRAPHQL_URL = "/graphql/"

    def setUp(self):
        self.therapist = User.objects.create_user(
            username="therapist_session", 
            email="ts@cbm.com", 
            password="pass",
            ci="22222222"
        )
        self.therapist.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="therapeutic_sessions",
            content_type__model="session",
            codename__in=("add_session", "change_session", "view_session", "delete_session"),
        ))
        self.client.force_login(self.therapist)
        self.patient = Patient.objects.create(first_name="Leo", last_name="Messi")
        PatientClinicalNote.objects.create(
            patient=self.patient,
            author=self.therapist,
            category=PatientClinicalNote.Category.GENERAL_OBJECTIVE,
            content="Inicial",
        )

    def _execute_query(self, query, variables=None):
        response = self.query(query, variables=variables)
        return response

    def test_create_session_calculates_cycle(self):
        """Prueba que la sesión se asigne al ciclo correcto (1-4 -> Ciclo 1, 5-8 -> Ciclo 2)"""
        mutation = """
            mutation CreateSession($patientId: ID!, $therapistId: ID!, $date: DateTime!, $type: String!) {
                createSession(patientId: $patientId, therapistId: $therapistId, sessionDate: $date, sessionType: $type) {
                    session { sessionNumber cycleNumber }
                }
            }
        """
        # Crear 5 sesiones para el mismo paciente
        from django.utils import timezone
        for i in range(1, 6):
            variables = {
                "patientId": str(self.patient.id),
                "therapistId": str(self.therapist.id),
                "date": timezone.now().isoformat(),
                "type": "individual"
            }
            response = self._execute_query(mutation, variables=variables)
            self.assertResponseNoErrors(response)
            
            content = json.loads(response.content)
            data = content["data"]["createSession"]["session"]
            
            if i <= 4:
                self.assertEqual(data["cycleNumber"], 1)
            else:
                self.assertEqual(data["cycleNumber"], 2)

    def test_patient_cycles_query(self):
        """Prueba que la query de ciclos agrupe correctamente las sesiones"""
        from django.utils import timezone
        # Crear 2 sesiones pagadas y 1 pendiente
        Session.objects.create(
            patient=self.patient, 
            therapist=self.therapist, 
            session_date=timezone.now(),
            session_type="individual",
            session_number=1,
            cycle_number=1,
            payment_status="paid"
        )
        Session.objects.create(
            patient=self.patient, 
            therapist=self.therapist, 
            session_date=timezone.now(),
            session_type="individual",
            session_number=2,
            cycle_number=1,
            payment_status="paid"
        )
        Session.objects.create(
            patient=self.patient, 
            therapist=self.therapist, 
            session_date=timezone.now(),
            session_type="individual",
            session_number=3,
            cycle_number=1,
            payment_status="pending"
        )

        query = """
            query GetCycles($patientId: ID!) {
                patientCycles(patientId: $patientId) {
                    cycleNumber
                    sessionCount
                    paymentSummary {
                        paid
                        pending
                    }
                }
            }
        """
        variables = {"patientId": str(self.patient.id)}
        response = self._execute_query(query, variables=variables)
        self.assertResponseNoErrors(response)
        
        content = json.loads(response.content)
        cycle = content["data"]["patientCycles"][0]
        
        self.assertEqual(cycle["cycleNumber"], 1)
        self.assertEqual(cycle["sessionCount"], 3)
        self.assertEqual(cycle["paymentSummary"]["paid"], 2)
        self.assertEqual(cycle["paymentSummary"]["pending"], 1)

    def test_sessions_query_filters_by_therapist_and_paginates(self):
        other = User.objects.create_user(
            username="other_therapist",
            email="other@cbm.com",
            password="pass",
            ci="77777777",
        )
        Session.objects.create(
            patient=self.patient,
            therapist=self.therapist,
            session_date=timezone.now(),
            session_type="individual",
            session_number=1,
            cycle_number=1,
            payment_status="pending",
        )
        other_patient = Patient.objects.create(first_name="Other", last_name="Patient")
        Session.objects.create(
            patient=other_patient,
            therapist=other,
            session_date=timezone.now(),
            session_type="individual",
            session_number=1,
            cycle_number=1,
            payment_status="pending",
        )

        query = """
            query Sessions($therapistId: ID!) {
                sessions(therapistId: $therapistId, page: 1, pageSize: 1) {
                    totalCount
                    totalPages
                    currentPage
                    sessions { therapist { username } }
                }
            }
        """
        content = self._execute_query(query, variables={"therapistId": str(self.therapist.id)})
        sessions = json.loads(content.content)["data"]["sessions"]

        self.assertEqual(sessions["totalCount"], 1)
        self.assertEqual(sessions["totalPages"], 1)
        self.assertEqual(sessions["currentPage"], 1)
        self.assertEqual(sessions["sessions"][0]["therapist"]["username"], self.therapist.username)

    def test_sessions_query_rejects_other_therapist_for_non_staff_user(self):
        other = User.objects.create_user(
            username="blocked_therapist",
            email="blocked@cbm.com",
            password="pass",
            ci="99999999",
        )
        query = """
            query Sessions($therapistId: ID!) {
                sessions(therapistId: $therapistId) { totalCount }
            }
        """

        response = self._execute_query(query, variables={"therapistId": str(other.id)})
        content = json.loads(response.content)

        self.assertEqual(content["errors"][0]["message"], "No autorizado.")

    def test_update_session_rejects_session_owned_by_other_therapist(self):
        other = User.objects.create_user(
            username="session_owner",
            email="session.owner@cbm.com",
            password="pass",
            ci="14141414",
        )
        session = Session.objects.create(
            patient=self.patient,
            therapist=other,
            session_date=timezone.now(),
            session_type="individual",
        )
        mutation = """
            mutation UpdateSession($id: ID!) {
                updateSession(id: $id, notes: "Forbidden") {
                    session { notes }
                }
            }
        """

        content = json.loads(self._execute_query(
            mutation, variables={"id": str(session.id)}
        ).content)

        self.assertEqual(content["errors"][0]["message"], "No autorizado.")
