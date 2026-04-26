import json
from decimal import Decimal
from django.test import TestCase
from graphene_django.utils.testing import GraphQLTestCase
from config.schema import schema
from clinical.models import Patient
from finance.models import Discount, Payment

class FinanceMutationTests(GraphQLTestCase):
    GRAPHQL_SCHEMA = schema
    GRAPHQL_URL = "/graphql/"

    def setUp(self):
        self.patient = Patient.objects.create(first_name="Leo", last_name="Finance")
        self.discount_pct = Discount.objects.create(
            name="Promo 10%",
            type="percentage",
            value=Decimal("10.00")
        )

    def test_create_payment_completed(self):
        """Prueba que un pago total resulte en estado COMPLETED"""
        mutation = """
            mutation CreatePayment($patientId: ID!, $count: Int!, $price: Float!, $paid: Float!, $method: String!) {
                createPayment(patientId: $patientId, sessionsCount: $count, pricePerSession: $price, amountPaid: $paid, paymentMethod: $method) {
                    payment { paymentStatus }
                }
            }
        """
        variables = {
            "patientId": str(self.patient.id),
            "count": 4,
            "price": 100.0,
            "paid": 400.0,
            "method": "cash"
        }
        response = self.query(mutation, variables=variables)
        self.assertResponseNoErrors(response)
        
        content = json.loads(response.content)
        self.assertEqual(content["data"]["createPayment"]["payment"]["paymentStatus"].lower(), "completed")

    def test_create_payment_with_discount(self):
        """Prueba que el descuento se aplique correctamente al estado del pago"""
        mutation = """
            mutation CreatePayment($patientId: ID!, $count: Int!, $price: Float!, $paid: Float!, $method: String!, $discountId: ID) {
                createPayment(patientId: $patientId, sessionsCount: $count, pricePerSession: $price, amountPaid: $paid, paymentMethod: $method, discountId: $discountId) {
                    payment { paymentStatus }
                }
            }
        """
        # Total base: 4 * 100 = 400. Con 10% desc = 360.
        variables = {
            "patientId": str(self.patient.id),
            "count": 4,
            "price": 100.0,
            "paid": 360.0, # Pago justo el total con descuento
            "method": "transfer",
            "discountId": str(self.discount_pct.id)
        }
        response = self.query(mutation, variables=variables)
        self.assertResponseNoErrors(response)
        
        content = json.loads(response.content)
        # Debería ser 'completed' porque pagó los 360 resultantes del descuento
        self.assertEqual(content["data"]["createPayment"]["payment"]["paymentStatus"].lower(), "completed")

    def test_query_payments_resolver(self):
        """Prueba que los resolvers (ahora dentro de la clase) funcionen"""
        Payment.objects.create(
            patient=self.patient,
            sessions_count=1,
            price_per_session=100,
            amount_paid=100,
            payment_method="cash",
            payment_status="completed"
        )
        
        query = """
            query {
                payments {
                    paymentStatus
                    patient { firstName }
                }
            }
        """
        response = self.query(query)
        self.assertResponseNoErrors(response)
        
        content = json.loads(response.content)
        self.assertTrue(len(content["data"]["payments"]) > 0)
        self.assertEqual(content["data"]["payments"][0]["patient"]["firstName"], "Leo")
