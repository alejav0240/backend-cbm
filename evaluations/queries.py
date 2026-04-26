import graphene
from graphql import GraphQLError

from evaluations.models import Scale, ScaleEvaluation, Form, FormAssignment
from evaluations.type import ScaleType, ScaleEvaluationType, FormType, FormAssignmentType


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
    )
    form_assignment = graphene.Field(FormAssignmentType, id=graphene.ID(required=True))

    # ── Resolvers escalas ─────────────────────────────────────
    def resolve_scales(self, info, scale_type=None):
        qs = Scale.objects.prefetch_related("subscales", "values").all()
        if scale_type:
            qs = qs.filter(scale_type=scale_type)
        return qs

    def resolve_scale(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        try:
            return Scale.objects.prefetch_related("subscales", "values").get(pk=real_id)
        except Scale.DoesNotExist:
            raise GraphQLError("Escala no encontrada")

    def resolve_scale_evaluations(self, info, patient_id=None, scale_id=None, in_session=None):
        qs = ScaleEvaluation.objects.select_related(
            "scale", "patient", "evaluator", "session"
        ).prefetch_related("subscale_responses", "value_responses")
        if patient_id:
            try:
                real_patient_id = int(graphene.relay.Node.from_global_id(patient_id)[1])
            except:
                real_patient_id = patient_id
            qs = qs.filter(patient_id=real_patient_id)
        if scale_id:
            try:
                real_scale_id = int(graphene.relay.Node.from_global_id(scale_id)[1])
            except:
                real_scale_id = scale_id
            qs = qs.filter(scale_id=real_scale_id)
        if in_session is True:
            qs = qs.exclude(session=None)
        elif in_session is False:
            qs = qs.filter(session=None)
        return qs

    def resolve_scale_evaluation(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        try:
            return ScaleEvaluation.objects.prefetch_related(
                "subscale_responses__subscale",
                "value_responses__scale_value",
            ).get(pk=real_id)
        except ScaleEvaluation.DoesNotExist:
            raise GraphQLError("Evaluación de escala no encontrada")

    # ── Resolvers formularios ─────────────────────────────────

    def resolve_forms(self, info, search=None):
        qs = Form.objects.prefetch_related("questions").all()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    def resolve_form(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        try:
            return Form.objects.prefetch_related("questions").get(pk=real_id)
        except Form.DoesNotExist:
            raise GraphQLError("Formulario no encontrado")

    def resolve_form_assignments(self, info, assigned_to_id=None, patient_id=None):
        qs = FormAssignment.objects.select_related(
            "form", "assigned_to", "assigned_by", "patient"
        ).prefetch_related("responses")
        if assigned_to_id:
            try:
                real_assigned_to_id = int(graphene.relay.Node.from_global_id(assigned_to_id)[1])
            except:
                real_assigned_to_id = assigned_to_id
            qs = qs.filter(assigned_to_id=real_assigned_to_id)
        if patient_id:
            try:
                real_patient_id = int(graphene.relay.Node.from_global_id(patient_id)[1])
            except:
                real_patient_id = patient_id
            qs = qs.filter(patient_id=real_patient_id)
        return qs

    def resolve_form_assignment(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        try:
            return FormAssignment.objects.prefetch_related("responses__question").get(pk=real_id)
        except FormAssignment.DoesNotExist:
            raise GraphQLError("Asignación de formulario no encontrada")

