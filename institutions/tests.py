import json
from django.test import TestCase
from graphene_django.utils.testing import GraphQLTestCase
from config.schema import schema
from institutions.models import Institution, InstitutionGroup

class InstitutionTests(GraphQLTestCase):
    GRAPHQL_SCHEMA = schema
    GRAPHQL_URL = "/graphql/"

    def test_create_institution(self):
        """Prueba la creación de una institución y el mapeo del campo phone"""
        mutation = """
            mutation Create($name: String!, $phone: String) {
                createInstitution(name: $name, phone: $phone) {
                    institution { name contactPhone }
                }
            }
        """
        variables = {
            "name": "Clinica Central",
            "phone": "555-1234"
        }
        response = self.query(mutation, variables=variables)
        self.assertResponseNoErrors(response)
        
        content = json.loads(response.content)
        data = content["data"]["createInstitution"]["institution"]
        self.assertEqual(data["name"], "Clinica Central")
        self.assertEqual(data["contactPhone"], "555-1234")
        
        # Verificar en DB que el campo real es contact_phone
        inst = Institution.objects.get(name="Clinica Central")
        self.assertEqual(inst.contact_phone, "555-1234")

    def test_create_group(self):
        """Prueba la creación de un grupo dentro de una institución"""
        inst = Institution.objects.create(name="Hospital A", contact_name="Admin")
        
        mutation = """
            mutation CreateGroup($instId: ID!, $name: String!) {
                createInstitutionGroup(institutionId: $instId, name: $name) {
                    group { id name institution { name } }
                }
            }
        """
        variables = {
            "instId": str(inst.id),
            "name": "Sala 1"
        }
        response = self.query(mutation, variables=variables)
        self.assertResponseNoErrors(response)
        
        content = json.loads(response.content)
        data = content["data"]["createInstitutionGroup"]["group"]
        self.assertEqual(data["name"], "Sala 1")
        self.assertEqual(data["institution"]["name"], "Hospital A")

    def test_query_institutions(self):
        """Prueba el listado de instituciones"""
        Institution.objects.create(name="Clinica X", contact_name="Dr. X")
        
        query = """
            query {
                institutions {
                    name
                }
            }
        """
        response = self.query(query)
        self.assertResponseNoErrors(response)
        content = json.loads(response.content)
        self.assertTrue(len(content["data"]["institutions"]) >= 1)
