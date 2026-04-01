import graphene

from therapeutic_sessions.models import Session, SessionResource, SessionInventory
from therapeutic_sessions.type import SessionType, SessionResourceType, SessionInventoryType


class CreateSession(graphene.Mutation):
    class Arguments:
        patient_id = graphene.ID(required=True)
        therapist_id = graphene.ID(required=True)
        session_date = graphene.DateTime(required=True)
        session_type = graphene.String(required=True)
        duration_minutes = graphene.Int()
        cycle_number = graphene.Int()
        notes = graphene.String()
        group_id = graphene.ID()
        video_url = graphene.String()
        audio_url = graphene.String()

    session = graphene.Field(SessionType)

    def mutate(self, info, patient_id, therapist_id, session_date, session_type,
               duration_minutes=None, cycle_number=None, notes=None,
               group_id=None, video_url=None, audio_url=None):
        session = Session.objects.create(
            patient_id=patient_id,
            therapist_id=therapist_id,
            session_date=session_date,
            session_type=session_type,
            duration_minutes=duration_minutes,
            cycle_number=cycle_number,
            notes=notes,
            group_id=group_id,
            video_url=video_url,
            audio_url=audio_url,
        )
        return CreateSession(session=session)


class UpdateSessionPaymentStatus(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        payment_status = graphene.String(required=True)

    session = graphene.Field(SessionType)

    def mutate(self, info, id, payment_status):
        session = Session.objects.get(pk=id)
        session.payment_status = payment_status
        session.save(update_fields=["payment_status", "updated_at"])
        return UpdateSessionPaymentStatus(session=session)


class AddSessionResource(graphene.Mutation):
    class Arguments:
        session_id = graphene.ID(required=True)
        resource_id = graphene.ID(required=True)

    session_resource = graphene.Field(SessionResourceType)

    def mutate(self, info, session_id, resource_id):
        sr, _ = SessionResource.objects.get_or_create(
            session_id=session_id, resource_id=resource_id
        )
        return AddSessionResource(session_resource=sr)


class AddSessionInventoryItem(graphene.Mutation):
    class Arguments:
        session_id = graphene.ID(required=True)
        item_id = graphene.ID(required=True)

    session_inventory = graphene.Field(SessionInventoryType)

    def mutate(self, info, session_id, item_id):
        si, _ = SessionInventory.objects.get_or_create(
            session_id=session_id, item_id=item_id
        )
        return AddSessionInventoryItem(session_inventory=si)

class Mutation(graphene.ObjectType):
    create_session = CreateSession.Field()
    update_session_payment_status = UpdateSessionPaymentStatus.Field()
    add_session_resource = AddSessionResource.Field()
    add_session_inventory_item = AddSessionInventoryItem.Field()