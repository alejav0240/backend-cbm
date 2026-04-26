import graphene
from graphql import GraphQLError
from .models import User, Notification
from .types import UserType, NotificationType


class Query(graphene.ObjectType):
    me = graphene.Field(UserType)
    users = graphene.List(UserType)
    user = graphene.Field(UserType, id=graphene.ID(required=True))

    notifications = graphene.List(
        NotificationType,
        is_read=graphene.Boolean(),
    )
    unread_notifications_count = graphene.Int()

    # ── me ──────────────────────────────────────────────────────────────────
    def resolve_me(root, info):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("No autenticado.")
        return user

    # ── users (solo staff) ──────────────────────────────────────────────────
    def resolve_users(root, info):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("No autenticado.")
        if not user.is_staff:
            raise GraphQLError("No autorizado: se requiere rol de administrador.")
        return User.objects.all()

    # ── user por id (solo staff o el propio usuario) ─────────────────────────
    def resolve_user(root, info, id):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("No autenticado.")
            
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id

        if not user.is_staff and str(user.pk) != str(real_id):
            raise GraphQLError("No autorizado.")
        try:
            return User.objects.get(pk=real_id)
        except User.DoesNotExist:
            raise GraphQLError(f"Usuario {real_id} no encontrado.")

    # ── notificaciones (solo las propias) ────────────────────────────────────
    def resolve_notifications(root, info, is_read=None):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("No autenticado.")
        qs = Notification.objects.filter(user=user)
        if is_read is not None:
            qs = qs.filter(is_read=is_read)
        return qs

    # ── contador rápido ──────────────────────────────────────────────────────
    def resolve_unread_notifications_count(root, info):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("No autenticado.")
        return Notification.objects.filter(user=user, is_read=False).count()