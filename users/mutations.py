# users/mutations.py

import graphene
import graphql_jwt
from graphql import GraphQLError

from .models import User, Notification
from .types import UserType, NotificationType


# ── Registro ────────────────────────────────────────────────────────────────
class CreateUser(graphene.Mutation):
    user = graphene.Field(UserType)

    class Arguments:
        username = graphene.String(required=True)
        email    = graphene.String(required=True)
        password = graphene.String(required=True)
        ci       = graphene.String(required=True)
        celular  = graphene.String()

    def mutate(self, info, username, email, password, ci, celular=""):
        if User.objects.filter(username=username).exists():
            raise GraphQLError("El nombre de usuario ya está en uso.")
        if User.objects.filter(email=email).exists():
            raise GraphQLError("El correo ya está registrado.")
        if User.objects.filter(ci=ci).exists():
            raise GraphQLError("El CI ya está registrado.")

        user = User(username=username, email=email, ci=ci, celular=celular)
        user.set_password(password)
        user.save()
        return CreateUser(user=user)

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

        # Manejar ID de Relay o ID directo y convertir a int
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            try:
                real_id = int(id)
            except:
                real_id = id

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
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            try:
                real_id = int(id)
            except:
                real_id = id
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

    # JWT Nativo
    token_auth = ObtainToken.Field()
    refresh_token = RefreshToken.Field()
    revoke_token = RevokeToken.Field()

    # Logout (Borrado de Cookies HttpOnly)
    delete_token_cookie = graphql_jwt.DeleteJSONWebTokenCookie.Field()
    delete_refresh_token_cookie = graphql_jwt.refresh_token.mutations.DeleteRefreshTokenCookie.Field()