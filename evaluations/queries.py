import graphene
from graphql import GraphQLError

from evaluations.models import Scale, ScaleEvaluation, Form, FormAssignment
from evaluations.type import ScaleType, ScaleEvaluationType, FormType, FormAssignmentType, PaginatedScaleEvaluations, PaginatedScales, PaginatedForms, PaginatedFormAssignments
from config.utils import module_permission_required, get_db_id


class Query(graphene.ObjectType):
    scales = graphene.Field(
        PaginatedScales,
        scale_type=graphene.String(),
        search=graphene.String(),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
    )
    scale = graphene.Field(ScaleType, id=graphene.ID(required=True))

    scale_evaluations = graphene.Field(
        PaginatedScaleEvaluations,
        patient_id=graphene.ID(),
        scale_id=graphene.ID(),
        in_session=graphene.Boolean(),
        search=graphene.String(description="Busca por nombre del paciente o nombre de la escala."),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
    )
    scale_evaluation = graphene.Field(ScaleEvaluationType, id=graphene.ID(required=True))

    # ── Evaluaciones — Formularios ────────────────────────────
    forms = graphene.Field(
        PaginatedForms,
        search=graphene.String(),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
    )
    form = graphene.Field(FormType, id=graphene.ID(required=True))

    form_assignments = graphene.Field(
        PaginatedFormAssignments,
        assigned_to_id=graphene.ID(),
        patient_id=graphene.ID(),
        form_id=graphene.ID(),
        session_id=graphene.ID(),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
    )
    form_assignment = graphene.Field(FormAssignmentType, id=graphene.ID(required=True))

    # ── Resolvers escalas ─────────────────────────────────────
    @module_permission_required('escalas', action='view')
    def resolve_scales(self, info, scale_type=None, search=None, page=1, page_size=10):
        qs = Scale.objects.prefetch_related("subscales", "values").all()
        if scale_type:
            qs = qs.filter(scale_type=scale_type)
        if search:
            qs = qs.filter(name__icontains=search)
        total_count = qs.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        offset = (page - 1) * page_size
        return PaginatedScales(
            results=qs[offset:offset + page_size],
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )

    @module_permission_required('escalas', action='view')
    def resolve_scale(self, info, id):
        real_id = get_db_id(id)
        try:
            return Scale.objects.prefetch_related("subscales", "values").get(pk=real_id)
        except Scale.DoesNotExist:
            raise GraphQLError("Escala no encontrada")

    @module_permission_required('evaluaciones', action='view')
    def resolve_scale_evaluations(self, info, patient_id=None, scale_id=None,
                                   in_session=None, search=None, page=1, page_size=10):
        from django.db.models import Q
        qs = ScaleEvaluation.objects.select_related(
            "scale", "patient", "evaluator", "session"
        ).prefetch_related("subscale_responses", "value_responses")
        if patient_id:
            qs = qs.filter(patient_id=get_db_id(patient_id))
        if scale_id:
            qs = qs.filter(scale_id=get_db_id(scale_id))
        if in_session is True:
            qs = qs.exclude(session=None)
        elif in_session is False:
            qs = qs.filter(session=None)
        if search:
            qs = qs.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search) |
                Q(scale__name__icontains=search)
            )

        total_count = qs.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        offset = (page - 1) * page_size

        return PaginatedScaleEvaluations(
            results=qs[offset:offset + page_size],
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )

    @module_permission_required('evaluaciones', action='view')
    def resolve_scale_evaluation(self, info, id):
        real_id = get_db_id(id)
        try:
            return ScaleEvaluation.objects.prefetch_related(
                "subscale_responses__subscale",
                "value_responses__scale_value",
            ).get(pk=real_id)
        except ScaleEvaluation.DoesNotExist:
            raise GraphQLError("Evaluación de escala no encontrada")

    # ── Resolvers formularios ─────────────────────────────────

    @module_permission_required('formularios', action='view')
    def resolve_forms(self, info, search=None, page=1, page_size=10):
        qs = Form.objects.prefetch_related("questions").all()
        if search:
            qs = qs.filter(name__icontains=search)
        total_count = qs.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        offset = (page - 1) * page_size
        return PaginatedForms(
            results=qs[offset:offset + page_size],
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )

    @module_permission_required('formularios', action='view')
    def resolve_form(self, info, id):
        real_id = get_db_id(id)
        try:
            return Form.objects.prefetch_related("questions").get(pk=real_id)
        except Form.DoesNotExist:
            raise GraphQLError("Formulario no encontrado")

    @module_permission_required('formularios', action='view')
    def resolve_form_assignments(self, info, assigned_to_id=None, patient_id=None,
                                  form_id=None, session_id=None, page=1, page_size=10):
        qs = FormAssignment.objects.select_related(
            "form", "assigned_to", "assigned_by", "patient", "session"
        ).prefetch_related("responses")
        if assigned_to_id:
            qs = qs.filter(assigned_to_id=get_db_id(assigned_to_id))
        if patient_id:
            qs = qs.filter(patient_id=get_db_id(patient_id))
        if form_id:
            qs = qs.filter(form_id=get_db_id(form_id))
        if session_id:
            qs = qs.filter(session_id=get_db_id(session_id))
        total_count = qs.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        offset = (page - 1) * page_size
        return PaginatedFormAssignments(
            results=qs[offset:offset + page_size],
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )

    @module_permission_required('formularios', action='view')
    def resolve_form_assignment(self, info, id):
        real_id = get_db_id(id)
        try:
            return FormAssignment.objects.prefetch_related("responses__question").get(pk=real_id)
        except FormAssignment.DoesNotExist:
            raise GraphQLError("Asignación de formulario no encontrada")
