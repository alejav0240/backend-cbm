import graphene
from graphql import GraphQLError
from django.contrib.auth.models import Group
from django.db.models import Q
from .models import User, Notification
from .types import UserType, NotificationType, RoleType
from config.utils import login_required, staff_member_required, get_db_id, module_permission_required


class PaginatedUsers(graphene.ObjectType):
    results = graphene.List(UserType)
    total_count = graphene.Int()
    total_pages = graphene.Int()
    current_page = graphene.Int()


class PaginatedRoles(graphene.ObjectType):
    results = graphene.List(RoleType)
    total_count = graphene.Int()
    total_pages = graphene.Int()
    current_page = graphene.Int()


class UserPatientSummaryType(graphene.ObjectType):
    """Paciente resumido para el contexto de un usuario."""
    id = graphene.ID()
    database_id = graphene.Int()
    full_name = graphene.String()
    diagnosis = graphene.String()
    status = graphene.String()
    relation = graphene.String(description="'therapist' | 'tutor'")


class UserWithPatientsType(graphene.ObjectType):
    """Usuario con la lista de pacientes que le están asociados."""
    user = graphene.Field(UserType)
    patients = graphene.List(UserPatientSummaryType)
    patients_count = graphene.Int()


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

    roles = graphene.Field(
        PaginatedRoles,
        search=graphene.String(),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
    )
    role = graphene.Field(RoleType, id=graphene.ID(required=True))

    notifications = graphene.List(
        NotificationType,
        is_read=graphene.Boolean(),
    )
    unread_notifications_count = graphene.Int()

    user_with_patients = graphene.Field(
        UserWithPatientsType,
        id=graphene.ID(required=True),
        description="Devuelve el usuario con todos los pacientes asociados (como terapeuta o tutor).",
    )

    @module_permission_required('roles', action='view')
    def resolve_roles(root, info, search=None, page=1, page_size=10):
        qs = Group.objects.all()
        if search:
            qs = qs.filter(name__icontains=search)
        total_count = qs.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        offset = (page - 1) * page_size
        return PaginatedRoles(
            results=qs[offset:offset + page_size],
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )

    @module_permission_required('roles', action='view')
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

    # ── users ───────────────────────────────────────────────────────────────
    @module_permission_required('usuarios', action='view')
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

        # Un usuario con permiso de ver 'usuarios' puede ver a cualquiera
        has_view_users = user.has_perm('users.view_user') or user.is_staff or user.is_superuser

        if not has_view_users and str(user.pk) != str(real_id):
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

    # ── usuario con sus pacientes asociados ──────────────────────────────────
    @module_permission_required('usuarios', action='view')
    def resolve_user_with_patients(root, info, id):
        from clinical.models import Patient
        from therapeutic_sessions.models import Session

        real_id = get_db_id(id)
        try:
            user = User.objects.get(pk=real_id)
        except User.DoesNotExist:
            raise GraphQLError(f"Usuario {real_id} no encontrado.")

        seen_ids = {}  # patient_id → relation

        # Pacientes donde es terapeuta (via sesiones)
        therapist_patient_ids = (
            Session.objects
            .filter(therapist_id=real_id, patient__isnull=False)
            .values_list("patient_id", flat=True)
            .distinct()
        )
        for pid in therapist_patient_ids:
            seen_ids[pid] = "therapist"

        # Pacientes donde es tutor (relación directa)
        tutor_patient_ids = (
            Patient.objects
            .filter(tutor_id=real_id)
            .values_list("id", flat=True)
        )
        for pid in tutor_patient_ids:
            if pid not in seen_ids:
                seen_ids[pid] = "tutor"

        if not seen_ids:
            return UserWithPatientsType(user=user, patients=[], patients_count=0)

        patients_qs = Patient.objects.filter(id__in=seen_ids.keys()).only(
            "id", "first_name", "last_name", "diagnosis", "status"
        )

        patient_list = []
        for p in patients_qs:
            global_id = graphene.relay.Node.to_global_id("PatientType", p.pk)
            patient_list.append(
                UserPatientSummaryType(
                    id=global_id,
                    database_id=p.pk,
                    full_name=f"{p.first_name} {p.last_name}",
                    diagnosis=p.diagnosis,
                    status=p.status,
                    relation=seen_ids[p.pk],
                )
            )

        patient_list.sort(key=lambda x: x.full_name)

        return UserWithPatientsType(
            user=user,
            patients=patient_list,
            patients_count=len(patient_list),
        )
