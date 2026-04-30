from django.contrib import admin
from django.urls import path
from graphql_jwt.decorators import jwt_cookie
from graphene_django.views import GraphQLView

urlpatterns = [
    path('admin/', admin.site.urls),
    path("graphql/", jwt_cookie(GraphQLView.as_view(graphiql=True))),
]