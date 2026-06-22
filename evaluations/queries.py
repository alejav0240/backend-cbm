import graphene
from graphql import GraphQLError

from evaluations.models import Scale, ScaleEvaluation, Form, FormAssignment
from evaluations.type import ScaleType, ScaleEvaluationType, FormType, FormAssignmentType
from config.utils import module_permission_required, get_db_id


class Query(graphene.ObjectType):
    scales = graphene.List(ScaleType, scale_type=graphene.String())
    scale = graphene.Field(ScaleType, id=graphene.ID(required=True))

    scale_evaluations = graphene.List(
        ScaleEvaluationType,
        patient_id=graphene.ID(),
        scale_id=graphene.ID(),
        in_session=graphene.Boolean(),
    )
    scale_evaluation = graphene.Field(ScaleEvaluationType, id=graphene.ID(required=True))

    # ── Evaluaciones — Formularios ────────────────────────────
    forms = graphene.List(FormType, search=graphene.String())
    form = graphene.Field(FormType, id=graphene.ID(required=True))

    form_assignments = graphene.List(
        FormAssignmentType,
        assigned_to_id=graphene.ID(),
        patient_id=graphene.ID(),
        form_id=graphene.ID(),
        session_id=graphene.ID(),
    )
    form_assignment = graphene.Field(FormAssignmentType, id=graphene.ID(required=True))

    # ── Resolvers escalas ─────────────────────────────────────
    @module_permission_required('escalas', action='view')
    def resolve_scales(self, info, scale_type=None):
        qs = Scale.objects.prefetch_related("subscales", "values").all()
        if scale_type:
            qs = qs.filter(scale_type=scale_type)
        return qs

    @module_permission_required('escalas', action='view')
    def resolve_scale(self, info, id):
        real_id = get_db_id(id)
        try:
            return Scale.objects.prefetch_related("subscales", "values").get(pk=real_id)
        except Scale.DoesNotExist:
            raise GraphQLError("Escala no encontrada")

    @module_permission_required('evaluaciones', action='view')
    def resolve_scale_evaluations(self, info, patient_id=None, scale_id=None, in_session=None):
        qs = ScaleEvaluation.objects.select_related(
            "scale", "patient", "evaluator", "session"
        ).prefetch_related("subscale_responses", "value_responses")
        if patient_id:
            real_patient_id = get_db_id(patient_id)
            qs = qs.filter(patient_id=real_patient_id)
        if scale_id:
            real_scale_id = get_db_id(scale_id)
            qs = qs.filter(scale_id=real_scale_id)
        if in_session is True:
            qs = qs.exclude(session=None)
        elif in_session is False:
            qs = qs.filter(session=None)
        return qs

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
    def resolve_forms(self, info, search=None):
        qs = Form.objects.prefetch_related("questions").all()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    @module_permission_required('formularios', action='view')
    def resolve_form(self, info, id):
        real_id = get_db_id(id)
        try:
            return Form.objects.prefetch_related("questions").get(pk=real_id)
        except Form.DoesNotExist:
            raise GraphQLError("Formulario no encontrado")

    @module_permission_required('formularios', action='view')
    def resolve_form_assignments(self, info, assigned_to_id=None, patient_id=None, form_id=None, session_id=None):
        qs = FormAssignment.objects.select_related(
            "form", "assigned_to", "assigned_by", "patient", "session"
        ).prefetch_related("responses")

        if assigned_to_id:
            real_assigned_to_id = get_db_id(assigned_to_id)
            qs = qs.filter(assigned_to_id=real_assigned_to_id)

        if patient_id:
            real_patient_id = get_db_id(patient_id)
            qs = qs.filter(patient_id=real_patient_id)

        if form_id:
            real_form_id = get_db_id(form_id)
            qs = qs.filter(form_id=real_form_id)

        if session_id:
            real_session_id = get_db_id(session_id)
            qs = qs.filter(session_id=real_session_id)

        return qs

    @module_permission_required('formularios', action='view')
    def resolve_form_assignment(self, info, id):
        real_id = get_db_id(id)
        try:
            return FormAssignment.objects.prefetch_related("responses__question").get(pk=real_id)
        except FormAssignment.DoesNotExist:
            raise GraphQLError("Asignación de formulario no encontrada")
