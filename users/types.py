# users/types.py
import graphene
from graphene_django import DjangoObjectType
from django.contrib.auth.models import Group
from users.models import User, Notification
from users.permissions_map import get_modules_for_group


class RoleType(DjangoObjectType):
    users_count = graphene.Int()
    permissions = graphene.List(graphene.String)

    class Meta:
        model = Group
        fields = ("id", "name")

    def resolve_users_count(self, info):
        return self.user_set.count()
        
    def resolve_permissions(self, info):
        # Traduce los permisos de Django a los módulos de la UI
        return get_modules_for_group(self)


class UserType(DjangoObjectType):
    database_id = graphene.Int()
    full_name = graphene.String()
    
    # Exponemos el primer grupo como 'role' para retrocompatibilidad simple si se desea
    role = graphene.Field(RoleType)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "ci",
            "celular",
            "status",
            "visibility",
            "foto",
            "cv",
            "is_active",
            "date_joined",
            "is_staff",
            "groups"
        )

    def resolve_database_id(self, info):
        return self.pk

    def resolve_full_name(self, info):
        return f"{self.first_name} {self.last_name}".strip()
        
    def resolve_role(self, info):
        return self.groups.first()


class NotificationType(DjangoObjectType):
    class Meta:
        model = Notification
        fields = ("id", "user", "message", "is_read", "created_at")
