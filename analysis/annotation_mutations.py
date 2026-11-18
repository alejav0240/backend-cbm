import graphene
from django.utils import timezone
from graphql import GraphQLError

from config.utils import get_db_id, module_permission_required, user_can_access_session

from .annotation_models import Adjudication, AnnotationCase, AnnotationReview, ParticipantAnchor
from .models import ProcessingRun
from .annotation_type import AnnotationCaseType, ParticipantAnchorType


def _case_for_user(info, case_id):
    try:
        case = AnnotationCase.objects.select_related("run__session").get(pk=get_db_id(case_id))
    except AnnotationCase.DoesNotExist as error:
        raise GraphQLError("Caso de anotación no encontrado.") from error
    if not user_can_access_session(info.context.user, case.run.session_id):
        raise GraphQLError("No autorizado.")
    return case


class ReviewAnnotationCase(graphene.Mutation):
    class Arguments:
        case_id = graphene.ID(required=True)
        decision = graphene.String(required=True)
        label = graphene.String()
        actor_role = graphene.String()
        start_seconds = graphene.Float()
        end_seconds = graphene.Float()
        comment = graphene.String()

    case = graphene.Field(AnnotationCaseType)

    @module_permission_required("sesiones", action="change")
    def mutate(self, info, case_id, decision, label="", actor_role="", start_seconds=None, end_seconds=None, comment=""):
        case = _case_for_user(info, case_id)
        if decision not in {choice for choice, _ in AnnotationReview.Decision.choices}:
            raise GraphQLError("Decisión de revisión inválida.")

        AnnotationReview.objects.update_or_create(
            case=case,
            reviewer=info.context.user,
            defaults={
                "decision": decision,
                "label": label or case.label,
                "actor_role": actor_role or case.actor_role,
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
                "comment": comment or "",
            },
        )

        reviews = list(case.reviews.values_list("decision", flat=True))
        if decision == AnnotationReview.Decision.REJECT:
            case.status = AnnotationCase.Status.REJECTED
        elif len(set(reviews)) > 1:
            case.status = AnnotationCase.Status.NEEDS_ADJUDICATION
        else:
            case.status = AnnotationCase.Status.ACCEPTED
        case.save(update_fields=["status", "updated_at"])
        return ReviewAnnotationCase(case=case)


class AdjudicateAnnotationCase(graphene.Mutation):
    class Arguments:
        case_id = graphene.ID(required=True)
        final_decision = graphene.String(required=True)
        final_label = graphene.String()
        final_actor_role = graphene.String()
        rationale = graphene.String()

    case = graphene.Field(AnnotationCaseType)

    @module_permission_required("sesiones", action="change")
    def mutate(self, info, case_id, final_decision, final_label="", final_actor_role="", rationale=""):
        case = _case_for_user(info, case_id)
        Adjudication.objects.update_or_create(
            case=case,
            defaults={
                "adjudicator": info.context.user,
                "final_decision": final_decision,
                "final_label": final_label or case.label,
                "final_actor_role": final_actor_role or case.actor_role,
                "rationale": rationale or "",
                "adjudicated_at": timezone.now(),
            },
        )
        case.status = (
            AnnotationCase.Status.ACCEPTED
            if final_decision == AnnotationReview.Decision.ACCEPT
            else AnnotationCase.Status.REJECTED
        )
        case.save(update_fields=["status", "updated_at"])
        return AdjudicateAnnotationCase(case=case)


class AssignParticipantAnchor(graphene.Mutation):
    class Arguments:
        run_id = graphene.ID(required=True)
        track_id = graphene.String(required=True)
        role = graphene.String(required=True)
        anchor_seconds = graphene.Float(required=True)
        patient_id = graphene.ID()
        therapist_id = graphene.ID()
        bounding_box = graphene.JSONString()
        confidence = graphene.Float()

    anchor = graphene.Field(ParticipantAnchorType)

    @module_permission_required("sesiones", action="change")
    def mutate(self, info, run_id, track_id, role, anchor_seconds, patient_id=None, therapist_id=None, bounding_box=None, confidence=None):
        run = ProcessingRun.objects.select_related("session").filter(pk=get_db_id(run_id)).first()
        if not run or not user_can_access_session(info.context.user, run.session_id):
            raise GraphQLError("No autorizado.")
        anchor, _ = ParticipantAnchor.objects.update_or_create(
            run=run,
            track_id=track_id,
            defaults={
                "role": role,
                "patient_id": get_db_id(patient_id) if patient_id else None,
                "therapist_id": get_db_id(therapist_id) if therapist_id else None,
                "anchor_seconds": anchor_seconds,
                "bounding_box": bounding_box if isinstance(bounding_box, dict) else {},
                "confidence": confidence,
                "reviewed_by": info.context.user,
            },
        )
        return AssignParticipantAnchor(anchor=anchor)


class AnnotationMutation(graphene.ObjectType):
    review_annotation_case = ReviewAnnotationCase.Field()
    adjudicate_annotation_case = AdjudicateAnnotationCase.Field()
    assign_participant_anchor = AssignParticipantAnchor.Field()
