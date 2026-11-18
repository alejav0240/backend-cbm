import graphene
from graphene_django import DjangoObjectType

from .annotation_models import Adjudication, AnnotationCase, AnnotationReview, ParticipantAnchor


class ParticipantAnchorType(DjangoObjectType):
    class Meta:
        model = ParticipantAnchor
        fields = (
            "id", "run", "track_id", "role", "patient", "therapist",
            "anchor_seconds", "bounding_box", "confidence", "reviewed_by", "reviewed_at",
        )

    bounding_box_json = graphene.JSONString()

    def resolve_bounding_box_json(self, info):
        return self.bounding_box


class AnnotationReviewType(DjangoObjectType):
    class Meta:
        model = AnnotationReview
        fields = (
            "id", "case", "reviewer", "decision", "label", "actor_role",
            "start_seconds", "end_seconds", "comment", "reviewed_at",
        )


class AdjudicationType(DjangoObjectType):
    class Meta:
        model = Adjudication
        fields = (
            "id", "case", "adjudicator", "final_decision", "final_label",
            "final_actor_role", "rationale", "adjudicated_at",
        )


class AnnotationCaseType(DjangoObjectType):
    class Meta:
        model = AnnotationCase
        fields = (
            "id", "run", "window_id", "start_seconds", "end_seconds",
            "modality", "label", "actor_role", "source", "status",
            "proposal_json", "created_at", "updated_at", "reviews", "adjudication",
        )

    proposal = graphene.JSONString()

    def resolve_proposal(self, info):
        return self.proposal_json
