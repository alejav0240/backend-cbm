# users/mutations.py

import graphene
import graphql_jwt
from graphql import GraphQLError
from django.contrib.auth.models import Group
from django.db import transaction

from .models import User, Notification
from .types import UserType, NotificationType, RoleType
from .permissions_map import get_permissions_for_modules
from config.utils import get_db_id


class CreateRole(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        permissions = graphene.List(graphene.String)

    role = graphene.Field(RoleType)

    def mutate(self, info, name, permissions=None):
        if permissions is None:
            permissions = []
        if Group.objects.filter(name=name).exists():
            raise GraphQLError("El rol ya existe")
        
        with transaction.atomic():
            group = Group.objects.create(name=name)
            # Traducir módulos de UI a Permisos de Django
            perms = get_permissions_for_modules(permissions)
            if perms:
                group.permissions.set(perms)
                
        return CreateRole(role=group)

class UpdateRole(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        name = graphene.String()
        permissions = graphene.List(graphene.String)

    role = graphene.Field(RoleType)

    def mutate(self, info, id, **kwargs):
        real_id = get_db_id(id)
        try:
            group = Group.objects.get(pk=real_id)
            
            with transaction.atomic():
                if 'name' in kwargs and kwargs['name']:
                    group.name = kwargs['name']
                    group.save(update_fields=['name'])
                    
                if 'permissions' in kwargs:
                    perms = get_permissions_for_modules(kwargs['permissions'] or [])
                    group.permissions.set(perms)
                    
            return UpdateRole(role=group)
        except Group.DoesNotExist:
            raise GraphQLError("Rol no encontrado")

class DeleteRole(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    success = graphene.Boolean()

    def mutate(self, info, id):
        real_id = get_db_id(id)
        try:
            group = Group.objects.get(pk=real_id)
            group.delete()
            return DeleteRole(success=True)
        except Group.DoesNotExist:
            return DeleteRole(success=False)

# ── Registro ────────────────────────────────────────────────────────────────
class CreateUser(graphene.Mutation):
    user = graphene.Field(UserType)
    plain_password = graphene.String(description="Contraseña en texto plano, solo disponible al momento de la creación.")

    class Arguments:
        username   = graphene.String(required=True)
        password   = graphene.String(required=True)
        ci         = graphene.String(required=True)
        email      = graphene.String()
        first_name = graphene.String()
        last_name  = graphene.String()
        celular    = graphene.String()
        status     = graphene.String()
        visibility = graphene.String()
        is_active  = graphene.Boolean()
        is_staff   = graphene.Boolean()
        role_id    = graphene.ID(description="ID del grupo/rol a asignar al usuario.")

    def mutate(self, info, username, password, ci,
               email=None, first_name="", last_name="",
               celular="", status="active", visibility="public",
               is_active=True, is_staff=False, role_id=None):

        if User.objects.filter(username=username).exists():
            raise GraphQLError("El nombre de usuario ya está en uso.")
        if email and User.objects.filter(email=email).exists():
            raise GraphQLError("El correo ya está registrado.")
        if User.objects.filter(ci=ci).exists():
            raise GraphQLError("El CI ya está registrado.")

        user = User(
            username   = username,
            email      = email,
            ci         = ci,
            first_name = first_name,
            last_name  = last_name,
            celular    = celular,
            status     = status,
            visibility = visibility,
            is_active  = is_active,
            is_staff   = is_staff,
        )
        user.set_password(password)
        user.save()

        if role_id:
            real_role_id = get_db_id(role_id)
            try:
                group = Group.objects.get(pk=real_role_id)
                user.groups.set([group])
            except Group.DoesNotExist:
                raise GraphQLError("Rol no encontrado.")

        return CreateUser(user=user, plain_password=password)

# ── Actualización ────────────────────────────────────────────────────────────
class UpdateUser(graphene.Mutation):
    user = graphene.Field(UserType)

    class Arguments:
        id         = graphene.ID(required=True)
        first_name = graphene.String()
        last_name  = graphene.String()
        email      = graphene.String()
        celular    = graphene.String()    # ← nombre correcto del campo
        ci         = graphene.String()
        visibility = graphene.String()
        is_active  = graphene.Boolean()

    def mutate(self, info, id, **kwargs):
        current_user = info.context.user
        if not current_user.is_authenticated:
            raise GraphQLError("No autenticado.")

        real_id = get_db_id(id)

        # Solo el propio usuario o un admin puede editar
        if not current_user.is_staff and str(current_user.pk) != str(real_id):
            raise GraphQLError("No autorizado.")

        try:
            user = User.objects.get(pk=real_id)
        except User.DoesNotExist:
            raise GraphQLError(f"Usuario {real_id} no encontrado.")

        # Solo staff puede cambiar is_active
        if "is_active" in kwargs and not current_user.is_staff:
            raise GraphQLError("No autorizado para cambiar el estado activo.")

        for field, value in kwargs.items():
            setattr(user, field, value)
        user.save()
        return UpdateUser(user=user)

# ── Cambio de contraseña ──────────────────────────────────────────────────────
class ChangePassword(graphene.Mutation):
    success = graphene.Boolean()

    class Arguments:
        old_password = graphene.String(required=True)
        new_password = graphene.String(required=True)

    def mutate(self, info, old_password, new_password):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("No autenticado.")
        if not user.check_password(old_password):
            raise GraphQLError("La contraseña actual es incorrecta.")
        if len(new_password) < 8:
            raise GraphQLError("La nueva contraseña debe tener al menos 8 caracteres.")

        user.set_password(new_password)
        user.save()
        return ChangePassword(success=True)

# ── Leer la notificacion ──────────────────────────────────────────────────────
class MarkNotificationRead(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    notification = graphene.Field(NotificationType)

    def mutate(self, info, id):
        real_id = get_db_id(id)
        notif = Notification.objects.get(pk=real_id)
        notif.is_read = True
        notif.save(update_fields=["is_read"])
        return MarkNotificationRead(notification=notif)


# ── Auth (JWT Nativo con Cookies) ─────────────────────────────────────────────

class ObtainToken(graphql_jwt.JSONWebTokenMutation):
    user = graphene.Field(UserType)

    @classmethod
    def resolve(cls, root, info, **kwargs):
        return cls(user=info.context.user)


class RefreshToken(graphql_jwt.Refresh):
    # La librería manejará la cookie de refresco automáticamente 
    # según la configuración en settings.py
    pass


class RevokeToken(graphql_jwt.Revoke):
    # Opcional: para invalidar refresh tokens en la DB
    pass


class Mutation(graphene.ObjectType):
    create_user = CreateUser.Field()
    update_user = UpdateUser.Field()
    change_password = ChangePassword.Field()
    mark_notification_read = MarkNotificationRead.Field()
    
    create_role = CreateRole.Field()
    update_role = UpdateRole.Field()
    delete_role = DeleteRole.Field()

    # JWT Nativo
    token_auth = ObtainToken.Field()
    refresh_token = RefreshToken.Field()
    revoke_token = RevokeToken.Field()

    # Logout (Borrado de Cookies HttpOnly)
    delete_token_cookie = graphql_jwt.DeleteJSONWebTokenCookie.Field()
    delete_refresh_token_cookie = graphql_jwt.refresh_token.mutations.DeleteRefreshTokenCookie.Field()