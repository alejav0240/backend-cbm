from django.contrib import admin
from django.urls import path
from graphql_jwt.decorators import jwt_cookie
from config.views import CBMGraphQLView

urlpatterns = [
    path('admin/', admin.site.urls),
    path("graphql/", jwt_cookie(CBMGraphQLView.as_view(graphiql=True))),
]