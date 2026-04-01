import graphene

from therapeutic_sessions.models import DigitalResource, Session, InventoryItem
from therapeutic_sessions.type import SessionType, DigitalResourceType, InventoryItemType


class Query(graphene.ObjectType):
    sessions = graphene.List(
        SessionType,
        patient_id=graphene.ID(),
        therapist_id=graphene.ID(),
        session_type=graphene.String(),
        payment_status=graphene.String(),
    )
    session = graphene.Field(SessionType, id=graphene.ID(required=True))

    digital_resources = graphene.List(
        DigitalResourceType,
        type=graphene.String(),
        search=graphene.String(),
    )
    digital_resource = graphene.Field(DigitalResourceType, id=graphene.ID(required=True))

    inventory_items = graphene.List(
        InventoryItemType,
        status=graphene.String(),
        type=graphene.String(),
    )
    inventory_item = graphene.Field(InventoryItemType, id=graphene.ID(required=True))

    def resolve_sessions(self, info, patient_id=None, therapist_id=None,
                         session_type=None, payment_status=None):
        qs = Session.objects.select_related("patient", "therapist", "group").all()
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        if therapist_id:
            qs = qs.filter(therapist_id=therapist_id)
        if session_type:
            qs = qs.filter(session_type=session_type)
        if payment_status:
            qs = qs.filter(payment_status=payment_status)
        return qs

    def resolve_session(self, info, id):
        return Session.objects.select_related(
            "patient", "therapist", "group"
        ).prefetch_related(
            "session_resources__resource",
            "session_inventory__item",
            "scale_evaluations",
        ).get(pk=id)

    def resolve_digital_resources(self, info, type=None, search=None):
        qs = DigitalResource.objects.all()
        if type:
            qs = qs.filter(type=type)
        if search:
            qs = qs.filter(title__icontains=search)
        return qs

    def resolve_digital_resource(self, info, id):
        return DigitalResource.objects.get(pk=id)

    def resolve_inventory_items(self, info, status=None, type=None):
        qs = InventoryItem.objects.all()
        if status:
            qs = qs.filter(status=status)
        if type:
            qs = qs.filter(type=type)
        return qs

    def resolve_inventory_item(self, info, id):
        return InventoryItem.objects.get(pk=id)