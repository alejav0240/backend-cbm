import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from graphene_django.utils.testing import GraphQLTestCase

from config.schema import schema


class GraphQLContractTests(GraphQLTestCase):
    GRAPHQL_SCHEMA = schema
    GRAPHQL_URL = "/graphql/"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="qa-graphql",
            email="graphql@example.com",
            password="safe-password",
            ci="QA-GQL-001",
        )

    def execute_json(self, query, variables=None):
        response = self.query(query, variables=variables)
        return response, json.loads(response.content)

    def test_protected_query_rejects_anonymous_user_without_500(self):
        response, payload = self.execute_json("query { me { username } }")
        self.assertEqual(response.status_code, 401)
        self.assertNotEqual(response.status_code, 500)
        self.assertIsNone(payload["data"]["me"])

    def test_token_auth_contract_does_not_expose_jwt_fields(self):
        response, payload = self.execute_json(
            """
            mutation TokenAuth($username: String!, $password: String!) {
              tokenAuth(username: $username, password: $password) {
                user { username }
              }
            }
            """,
            {"username": "qa-graphql", "password": "safe-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("errors", payload)
        self.assertEqual(payload["data"]["tokenAuth"]["user"]["username"], "qa-graphql")
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)
        self.assertTrue(response.cookies["access_token"]["httponly"])
        self.assertTrue(response.cookies["refresh_token"]["httponly"])

    def test_permissioned_query_filters_and_paginates(self):
        permission = Permission.objects.get(
            content_type__app_label="users",
            content_type__model="user",
            codename="view_user",
        )
        group = Group.objects.create(name="QA Users Viewer")
        group.permissions.add(permission)
        self.user.groups.add(group)
        get_user_model().objects.create_user(
            username="qa-other",
            email="other@example.com",
            password="safe-password",
            ci="QA-GQL-002",
        )
        self.client.force_login(self.user)

        response, payload = self.execute_json(
            """
            query Users($search: String!, $page: Int!, $pageSize: Int!) {
              users(search: $search, page: $page, pageSize: $pageSize) {
                totalCount totalPages currentPage results { username }
              }
            }
            """,
            {"search": "qa-", "page": 1, "pageSize": 1},
        )
        self.assertEqual(response.status_code, 200)
        result = payload["data"]["users"]
        self.assertEqual(result["currentPage"], 1)
        self.assertEqual(result["totalCount"], 2)
        self.assertEqual(len(result["results"]), 1)

    def test_business_validation_returns_graphql_error_not_server_error(self):
        response, payload = self.execute_json(
            """
            mutation CreateUser($username: String!, $email: String!, $password: String!, $ci: String!) {
              createUser(username: $username, email: $email, password: $password, ci: $ci) {
                user { username }
              }
            }
            """,
            {
                "username": "qa-duplicate",
                "email": "graphql@example.com",
                "password": "safe-password",
                "ci": "QA-GQL-003",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("errors", payload)
        self.assertNotEqual(response.status_code, 500)
