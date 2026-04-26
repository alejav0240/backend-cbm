import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
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

