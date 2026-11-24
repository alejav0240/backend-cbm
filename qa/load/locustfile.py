import os

from locust import HttpUser, between, task


GRAPHQL_QUERY = "query { __typename }"


class GraphQLUser(HttpUser):
    """Optional load scenario; excluded from Django unit-test discovery."""

    wait_time = between(1, 3)

    @task
    def introspection_smoke(self):
        self.client.post(
            os.getenv("GRAPHQL_PATH", "/graphql/"),
            json={"query": GRAPHQL_QUERY},
            headers={"X-Request-ID": "locust-graphql"},
            name="graphql typename",
        )
