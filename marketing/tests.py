import json
from decimal import Decimal
from django.test import TestCase
from graphene_django.utils.testing import GraphQLTestCase
from config.schema import schema
from marketing.models import MarketingCampaign, Lead

class MarketingTests(GraphQLTestCase):
    GRAPHQL_SCHEMA = schema
    GRAPHQL_URL = "/graphql/"

    def setUp(self):
        self.campaign = MarketingCampaign.objects.create(
            name="Facebook Ads Q1",
            platform="Facebook",
            budget=Decimal("1000.00"),
            spent=Decimal("200.00")
        )

    def test_create_campaign(self):
        """Prueba la creación de una campaña y la conversión de Float a Decimal"""
        mutation = """
            mutation Create($name: String!, $platform: String!, $budget: Float!) {
                createCampaign(name: $name, platform: $platform, budget: $budget) {
                    campaign { budget }
                }
            }
        """
        variables = {
            "name": "Google Ads",
            "platform": "Google",
            "budget": 500.50
        }
        response = self.query(mutation, variables=variables)
        self.assertResponseNoErrors(response)
        
        content = json.loads(response.content)
        # Graphene devuelve Decimal como String por defecto
        self.assertEqual(float(content["data"]["createCampaign"]["campaign"]["budget"]), 500.50)
        
        # Verificar en DB que es un Decimal exacto
        camp = MarketingCampaign.objects.get(name="Google Ads")
        self.assertEqual(camp.budget, Decimal("500.50"))

    def test_create_lead_with_campaign(self):
        """Prueba registrar un lead vinculado a una campaña"""
        mutation = """
            mutation CreateLead($name: String!, $campaignId: ID) {
                createLead(name: $name, campaignId: $campaignId) {
                    lead { name campaign { name } }
                }
            }
        """
        variables = {
            "name": "Cliente Interesado",
            "campaignId": str(self.campaign.id)
        }
        response = self.query(mutation, variables=variables)
        self.assertResponseNoErrors(response)
        
        content = json.loads(response.content)
        data = content["data"]["createLead"]["lead"]
        self.assertEqual(data["name"], "Cliente Interesado")
        self.assertEqual(data["campaign"]["name"], "Facebook Ads Q1")

    def test_campaign_remaining_budget_property(self):
        """Prueba que la propiedad remaining_budget se exponga correctamente (si está en el Type)"""
        query = """
            query GetCampaign($id: ID!) {
                marketingCampaign(id: $id) {
                    budget
                    spent
                    remainingBudget
                }
            }
        """
        variables = {"id": str(self.campaign.id)}
        response = self.query(query, variables=variables)
        self.assertResponseNoErrors(response)
        
        content = json.loads(response.content)
        data = content["data"]["marketingCampaign"]
        self.assertEqual(data["remainingBudget"], 800.00)
