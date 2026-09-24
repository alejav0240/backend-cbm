import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from graphene_django.utils.testing import GraphQLTestCase
from config.schema import schema

User = get_user_model()

class UsersMutationTests(GraphQLTestCase):
    GRAPHQL_SCHEMA = schema
    GRAPHQL_URL = "/graphql/"  # Especificamos la URL exacta con la barra final

    def setUp(self):
        self.user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "old_password_123",
            "ci": "12345678"
        }
        self.user = User.objects.create_user(**self.user_data)

    def _execute_query(self, query, variables=None):
        """Helper para ejecutar la consulta y depurar si falla el JSON"""
        response = self.query(query, variables=variables)
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            print(f"\nERROR: Respuesta no JSON (Status {response.status_code}):")
            print(response.content.decode('utf-8'))
            raise

    def test_create_user_mutation(self):
        """Prueba la creación de un nuevo usuario"""
        mutation = """
            mutation CreateUser($username: String!, $email: String!, $password: String!, $ci: String!) {
                createUser(username: $username, email: $email, password: $password, ci: $ci) {
                    user {
                        username
                        email
                        ci
                    }
                }
            }
        """
        variables = {
            "username": "newuser",
            "email": "new@example.com",
            "password": "securepassword123",
            "ci": "87654321"
        }
        content = self._execute_query(mutation, variables=variables)
        self.assertEqual(content["data"]["createUser"]["user"]["username"], "newuser")
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_create_user_duplicate_ci(self):
        """Prueba que no se pueda registrar un CI duplicado"""
        mutation = """
            mutation CreateUser($username: String!, $email: String!, $password: String!, $ci: String!) {
                createUser(username: $username, email: $email, password: $password, ci: $ci) {
                    user { username }
                }
            }
        """
        variables = {
            "username": "anotheruser",
            "email": "another@example.com",
            "password": "password123",
            "ci": "12345678"  # CI ya existe en setUp
        }
        content = self._execute_query(mutation, variables=variables)
        self.assertIn("errors", content)
        self.assertEqual(content["errors"][0]["message"], "El CI ya está registrado.")

    def test_token_auth_mutation(self):
        """Prueba el login (ObtainToken)"""
        mutation = """
            mutation TokenAuth($username: String!, $password: String!) {
                tokenAuth(username: $username, password: $password) {
                    user {
                        username
                    }
                }
            }
        """
        variables = {
            "username": "testuser",
            "password": "old_password_123"
        }
        content = self._execute_query(mutation, variables=variables)
        self.assertEqual(content["data"]["tokenAuth"]["user"]["username"], "testuser")

    def test_change_password_mutation(self):
        """Prueba que el fix de ChangePassword realmente guarde la contraseña"""
        mutation = """
            mutation ChangePassword($old: String!, $new: String!) {
                changePassword(oldPassword: $old, newPassword: $new) {
                    success
                }
            }
        """
        variables = {
            "old": "old_password_123",
            "new": "new_password_secure_456"
        }
        
        # Necesitamos estar autenticados para cambiar password
        self.client.force_login(self.user)
        
        content = self._execute_query(mutation, variables=variables)
        self.assertTrue(content["data"]["changePassword"]["success"])

        # Verificar que la contraseña realmente cambió en la DB
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new_password_secure_456"))

    def test_update_user_mutation(self):
        """Prueba la actualización de perfil"""
        mutation = """
            mutation UpdateUser($id: ID!, $firstName: String, $lastName: String) {
                updateUser(id: $id, firstName: $firstName, lastName: $lastName) {
                    user {
                        firstName
                        lastName
                    }
                }
            }
        """
        variables = {
            "id": str(self.user.id),
            "firstName": "Pepe",
            "lastName": "Grillo"
        }
        
        self.client.force_login(self.user)
        content = self._execute_query(mutation, variables=variables)
        self.assertEqual(content["data"]["updateUser"]["user"]["firstName"], "Pepe")
        
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Pepe")

    def test_onboarding_view_is_persisted_per_user_and_view(self):
        self.client.force_login(self.user)
        query = """
            query OnboardingView($viewKey: String!) {
                onboardingView(viewKey: $viewKey) {
                    viewKey
                    completedAt
                }
            }
        """
        mutation = """
            mutation MarkOnboardingViewSeen($viewKey: String!) {
                markOnboardingViewSeen(viewKey: $viewKey) {
                    onboardingView {
                        viewKey
                    }
                }
            }
        """
        variables = {"viewKey": "/dashboard/pacientes"}

        initial = self._execute_query(query, variables=variables)
        self.assertIsNone(initial["data"]["onboardingView"])

        marked = self._execute_query(mutation, variables=variables)
        self.assertEqual(
            marked["data"]["markOnboardingViewSeen"]["onboardingView"]["viewKey"],
            variables["viewKey"],
        )

        persisted = self._execute_query(query, variables=variables)
        self.assertEqual(
            persisted["data"]["onboardingView"]["viewKey"],
            variables["viewKey"],
        )

        self._execute_query(mutation, variables=variables)
        self.assertEqual(self.user.onboarding_views.count(), 1)

    def test_me_requires_authentication(self):
        query = """
            query {
                me { username }
            }
        """

        content = self._execute_query(query)

        self.assertIsNone(content["data"]["me"])
        self.assertEqual(content["errors"][0]["message"], "No autenticado.")

    def test_me_returns_role_and_modules_for_user_permissions(self):
        role = Group.objects.create(name="Terapeuta")
        permission = Permission.objects.get(
            content_type__app_label="users",
            content_type__model="user",
            codename="view_user",
        )
        role.permissions.add(permission)
        self.user.groups.add(role)
        self.client.force_login(self.user)

        query = """
            query {
                me {
                    username
                    role { name }
                    modules
                }
            }
        """

        content = self._execute_query(query)

        self.assertEqual(content["data"]["me"]["role"]["name"], "Terapeuta")
        self.assertIn("usuarios:view", content["data"]["me"]["modules"])

    def test_token_auth_sets_http_only_access_and_refresh_cookies(self):
        mutation = """
            mutation TokenAuth($username: String!, $password: String!) {
                tokenAuth(username: $username, password: $password) {
                    user { username }
                }
            }
        """

        response = self.query(
            mutation,
            variables={
                "username": "testuser",
                "password": "old_password_123",
            },
        )

        self.assertResponseNoErrors(response)
        self.assertEqual(response.cookies["access_token"].get("httponly"), True)
        self.assertEqual(response.cookies["refresh_token"].get("httponly"), True)

    def test_users_query_requires_module_permission(self):
        self.client.force_login(self.user)
        query = """
            query {
                users { results { username } }
            }
        """

        content = self._execute_query(query)

        self.assertIsNone(content["data"]["users"])
        self.assertIn("No tienes permiso", content["errors"][0]["message"])

    def test_refresh_and_logout_use_jwt_cookies(self):
        login = self.query(
            """
            mutation {
                tokenAuth(username: "testuser", password: "old_password_123") {
                    user { username }
                }
            }
            """
        )
        self.assertResponseNoErrors(login)
        self.client.cookies.update(login.cookies)
        # Refresh must use its valid refresh cookie even if access has expired.
        self.client.cookies["access_token"] = "expired-access-token"

        refreshed = self.query(
            """
            mutation { refreshToken { token refreshToken } }
            """
        )
        self.assertResponseNoErrors(refreshed)
        self.assertTrue(refreshed.json()["data"]["refreshToken"]["token"])
        self.assertTrue(refreshed.json()["data"]["refreshToken"]["refreshToken"])

        logged_out = self.query(
            """
            mutation {
                deleteTokenCookie { deleted }
                deleteRefreshTokenCookie { deleted }
            }
            """
        )
        self.assertResponseNoErrors(logged_out)
        self.assertTrue(logged_out.json()["data"]["deleteTokenCookie"]["deleted"])
        self.assertTrue(logged_out.json()["data"]["deleteRefreshTokenCookie"]["deleted"])
