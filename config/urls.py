from django.contrib import admin
from django.urls import path
from graphql_jwt.decorators import jwt_cookie
from config.views import CBMGraphQLView, csrf_token_view
from django.views.decorators.csrf import csrf_exempt

urlpatterns = [
    path('admin/', admin.site.urls),
    #path(
        #   "graphql/",
        #  csrf_exempt(
        #     CBMGraphQLView.as_view(graphiql=True)
        #),
    #),
    path("graphql/", jwt_cookie(CBMGraphQLView.as_view(graphiql=True))),
    path("csrf/", csrf_token_view),
]