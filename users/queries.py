import graphene
from graphql import GraphQLError
from django.contrib.auth.models import Group
from .models import User, Notification
from .types import UserType, NotificationType, RoleType


class PaginatedUsers(graphene.ObjectType):
    results = graphene.List(UserType)
    total_count = graphene.Int()
    total_pages = graphene.Int()
    current_page = graphene.Int()


class Query(graphene.ObjectType):
    me = graphene.Field(UserType)
    users = graphene.Field(
        PaginatedUsers,
        search=graphene.String(),
        role_name=graphene.String(),
        exclude_role=graphene.String(),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
    )
    user = graphene.Field(UserType, id=graphene.ID(required=True))

    roles = graphene.List(RoleType)
    role = graphene.Field(RoleType, id=graphene.ID(required=True))

    notifications = graphene.List(
        NotificationType,
        is_read=graphene.Boolean(),
    )
    unread_notifications_count = graphene.Int()

    def resolve_roles(root, info):
        return Group.objects.all()

    def resolve_role(root, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        try:
            return Group.objects.get(pk=real_id)
        except Group.DoesNotExist:
            raise GraphQLError("Rol no encontrado")

    # ── me ──────────────────────────────────────────────────────────────────
    def resolve_me(root, info):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("No autenticado.")
        return user

    # ── users (solo staff) ──────────────────────────────────────────────────
    def resolve_users(root, info, search=None, role_name=None, exclude_role=None, page=1, page_size=10):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("No autenticado.")
        if not user.is_staff:
            raise GraphQLError("No autorizado: se requiere rol de administrador.")
        
        qs = User.objects.all().order_by('-date_joined')
        
        if role_name:
            qs = qs.filter(groups__name__iexact=role_name)
        
        if exclude_role:
            qs = qs.exclude(groups__name__iexact=exclude_role)

        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(username__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(ci__icontains=search)
            )

        total_count = qs.count()
        total_pages = (total_count + page_size - 1) // page_size
        offset = (page - 1) * page_size
        results = qs[offset:offset + page_size]

        return PaginatedUsers(
            results=results,
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )

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