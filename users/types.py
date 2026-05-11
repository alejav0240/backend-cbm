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
    modules = graphene.List(graphene.String)
    
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

    def resolve_modules(self, info):
        from .permissions_map import MODULE_MODEL_MAP
        
        # Si es superusuario o staff, tiene todas las acciones en todos los módulos
        if self.is_superuser or self.is_staff:
            all_perms = []
            for mod in MODULE_MODEL_MAP.keys():
                for action in ['view', 'add', 'change', 'delete']:
                    all_perms.append(f"{mod}:{action}")
            return all_perms
            
        modules_actions = set()
        user_permissions = self.get_all_permissions() # Retorna set de 'app_label.codename'

        for mod, (app_label, model_name) in MODULE_MODEL_MAP.items():
            for action in ['view', 'add', 'change', 'delete']:
                perm_string = f"{app_label}.{action}_{model_name}"
                if perm_string in user_permissions:
                    modules_actions.add(f"{mod}:{action}")
                    
        return list(modules_actions)


class NotificationType(DjangoObjectType):
    class Meta:
        model = Notification
        fields = ("id", "user", "message", "is_read", "created_at")
