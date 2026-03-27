import graphene
from graphene_django import DjangoObjectType
from graphql import GraphQLError
from .models import User


class UserType(DjangoObjectType):
    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "carnet", "type", "phone", "status", "visibility")


class Query(graphene.ObjectType):
    me = graphene.Field(UserType)
    users = graphene.List(UserType)

    def resolve_me(root, info):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("No autenticado")
        return user

    def resolve_users(root, info):
        if not info.context.user.is_authenticated:
            raise GraphQLError("No autorizado")
        return User.objects.all()