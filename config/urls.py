from django.contrib import admin
from django.urls import include, path
from graphql_jwt.decorators import jwt_cookie
from config.views import CBMGraphQLView, application_encryption_key_view, csrf_token_view, health_view
from pipeline_multimodal.views import listar_modelos_openai
from django.views.decorators.csrf import csrf_exempt

urlpatterns = [
    path("health/", health_view, name="health"),
    path("v1/models", listar_modelos_openai, name="openai-model-list"),
    path('admin/', admin.site.urls),
    # path(
    #        "graphql/",
    #       csrf_exempt(
    #          CBMGraphQLView.as_view(graphiql=True)
    #     ),
    # ),
    path("graphql/", jwt_cookie(CBMGraphQLView.as_view(graphiql=True))),
    path("csrf/", csrf_token_view),
    path("crypto/public-key/", application_encryption_key_view),
    path("api/onedrive/", include("onedrive.urls")),
    path("api/multimodal/", include("multimodal.urls")),
    path("api/pipeline-multimodal/", include("pipeline_multimodal.urls")),
]
