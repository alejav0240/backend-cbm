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

        # Solo el propio usuario o un admin puede editar
        if not current_user.is_staff and str(current_user.pk) != str(id):
            raise GraphQLError("No autorizado.")

        try:
            user = User.objects.get(pk=id)
        except User.DoesNotExist:
            raise GraphQLError(f"Usuario {id} no encontrado.")

        # Solo staff puede cambiar is_active
        if "is_active" in kwargs and not current_user.is_staff:
            raise GraphQLError("No autorizado para cambiar el estado activo.")

        for field, value in kwargs.items():
            setattr(user, field, value)
        user.save()
        return UpdateUser(user=user)

# ── Cambio de contraseña ──────────────────────────────────────────────────────
class ChangePassword(graphene.Mutation):
    ok = graphene.Boolean()

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

# ── Leer la notificacion ──────────────────────────────────────────────────────
class MarkNotificationRead(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    notification = graphene.Field(NotificationType)

    def mutate(self, info, id):
        notif = Notification.objects.get(pk=id)
        notif.is_read = True
        notif.save(update_fields=["is_read"])
        return MarkNotificationRead(notification=notif)


class Mutation(graphene.ObjectType):
    create_user = CreateUser.Field()
    update_user = UpdateUser.Field()
    can_change_password = ChangePassword.Field()
    mark_notification_read = MarkNotificationRead.Field()

    # JWT
    token_auth = graphql_jwt.ObtainJSONWebToken.Field()
    verify_token = graphql_jwt.Verify.Field()
    refresh_token = graphql_jwt.Refresh.Field()