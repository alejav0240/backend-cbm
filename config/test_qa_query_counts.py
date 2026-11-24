from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection

from config.schema import schema


class GraphQLQueryCountTests(TestCase):
    def test_paginated_user_query_has_bounded_database_work(self):
        user_model = get_user_model()
        user = user_model.objects.create_superuser(
            username="qa-query-count",
            email="query-count@example.com",
            password="safe-password",
            ci="QA-COUNT-001",
        )
        for index in range(5):
            user_model.objects.create_user(
                username=f"qa-query-{index}",
                email=f"query-{index}@example.com",
                password="safe-password",
                ci=f"QA-COUNT-{index + 2:03d}",
            )

        query = """
        query {
          users(page: 1, pageSize: 5) {
            totalCount totalPages currentPage results { id username email }
          }
        }
        """
        with CaptureQueriesContext(connection) as captured:
            result = schema.execute(query, context_value=SimpleNamespace(user=user))

        self.assertFalse(result.errors, result.errors)
        self.assertEqual(len(result.data["users"]["results"]), 5)
        self.assertLessEqual(len(captured), 4)
        with self.assertNumQueries(1):
            list(user_model.objects.order_by("-date_joined")[:5])
