import graphene
from graphql import GraphQLError
from django.contrib.auth.models import Group
from .models import User, Notification
from .types import UserType, NotificationType, RoleType
from config.utils import login_required, staff_member_required, get_db_id


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
        real_id = get_db_id(id)
        try:
            return Group.objects.get(pk=real_id)
        except Group.DoesNotExist:
            raise GraphQLError("Rol no encontrado")

    # ── me ──────────────────────────────────────────────────────────────────
    @login_required
    def resolve_me(root, info):
        return info.context.user

    # ── users (solo staff) ──────────────────────────────────────────────────
    @staff_member_required
    def resolve_users(root, info, search=None, role_name=None, exclude_role=None, page=1, page_size=10):
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
    @login_required
    def resolve_user(root, info, id):
        user = info.context.user
        real_id = get_db_id(id)

        if not user.is_staff and str(user.pk) != str(real_id):
            raise GraphQLError("No autorizado.")
        try:
            return User.objects.get(pk=real_id)
        except User.DoesNotExist:
            raise GraphQLError(f"Usuario {real_id} no encontrado.")

    # ── notificaciones (solo las propias) ────────────────────────────────────
    @login_required
    def resolve_notifications(root, info, is_read=None):
        user = info.context.user
        qs = Notification.objects.filter(user=user)
        if is_read is not None:
            qs = qs.filter(is_read=is_read)
        return qs

    # ── contador rápido ──────────────────────────────────────────────────────
    @login_required
    def resolve_unread_notifications_count(root, info):
        user = info.context.user
        return Notification.objects.filter(user=user, is_read=False).count()
