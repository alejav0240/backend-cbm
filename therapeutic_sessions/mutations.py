import math
import graphene
from graphql import GraphQLError
from django.db.models.functions import Coalesce

from therapeutic_sessions.models import Session, SessionResource, SessionInventory
from therapeutic_sessions.type import SessionType, SessionResourceType, SessionInventoryType

from django.db.models import Max

class CreateSession(graphene.Mutation):
    class Arguments:
        patient_id = graphene.ID()
        therapist_id = graphene.ID(required=True)
        session_date = graphene.DateTime(required=True)
        session_type = graphene.String(required=True)
        duration_minutes = graphene.Int()
        notes = graphene.String()
        group_id = graphene.ID()
        video_url = graphene.String()

    session = graphene.Field(SessionType)

    def mutate(self, info, patient_id, therapist_id, session_date, session_type,
               duration_minutes=None, notes=None, group_id=None, video_url=None):
        
        # Manejar IDs de Relay
        try:
            real_patient_id = int(graphene.relay.Node.from_global_id(patient_id)[1])
        except:
            real_patient_id = patient_id

        try:
            real_therapist_id = int(graphene.relay.Node.from_global_id(therapist_id)[1])
        except:
            real_therapist_id = therapist_id

        # 1. Obtener el número de la última sesión del paciente
        last_session_data = Session.objects.filter(patient_id=real_patient_id).aggregate(
            last_num=Coalesce(Max('session_number'), 0)
        )

        current_session_number = last_session_data['last_num'] + 1

        calculated_cycle = math.ceil(current_session_number / 4)

        session = Session.objects.create(
            patient_id=real_patient_id,
            therapist_id=real_therapist_id,
            session_date=session_date,
            session_type=session_type,
            session_number=current_session_number,  # Guardamos el correlativo
            cycle_number=calculated_cycle,  # Guardamos el ciclo calculado
            duration_minutes=duration_minutes,
            notes=notes,
            group_id=group_id,
            video_url=video_url,
        )

        return CreateSession(session=session)


class UpdateSessionPaymentStatus(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        payment_status = graphene.String(required=True)

    session = graphene.Field(SessionType)

    def mutate(self, info, id, payment_status):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
            
        try:
            session = Session.objects.get(pk=real_id)
        except Session.DoesNotExist:
            raise GraphQLError("Sesión no encontrada")
        session.payment_status = payment_status
        session.save(update_fields=["payment_status", "updated_at"])
        return UpdateSessionPaymentStatus(session=session)


class AddSessionResource(graphene.Mutation):
    class Arguments:
        session_id = graphene.ID(required=True)
        resource_id = graphene.ID(required=True)

    session_resource = graphene.Field(SessionResourceType)

    def mutate(self, info, session_id, resource_id):
        try:
            real_session_id = int(graphene.relay.Node.from_global_id(session_id)[1])
        except:
            real_session_id = session_id

        try:
            real_resource_id = int(graphene.relay.Node.from_global_id(resource_id)[1])
        except:
            real_resource_id = resource_id

        sr, _ = SessionResource.objects.get_or_create(
            session_id=real_session_id, resource_id=real_resource_id
        )
        return AddSessionResource(session_resource=sr)


class AddSessionInventoryItem(graphene.Mutation):
    class Arguments:
        session_id = graphene.ID(required=True)
        item_id = graphene.ID(required=True)

    session_inventory = graphene.Field(SessionInventoryType)

    def mutate(self, info, session_id, item_id):
        try:
            real_session_id = int(graphene.relay.Node.from_global_id(session_id)[1])
        except:
            real_session_id = session_id

        try:
            real_item_id = int(graphene.relay.Node.from_global_id(item_id)[1])
        except:
            real_item_id = item_id

        si, _ = SessionInventory.objects.get_or_create(
            session_id=real_session_id, item_id=real_item_id
        )
        return AddSessionInventoryItem(session_inventory=si)

class Mutation(graphene.ObjectType):
    create_session = CreateSession.Field()
    update_session_payment_status = UpdateSessionPaymentStatus.Field()
    add_session_resource = AddSessionResource.Field()
    add_session_inventory_item = AddSessionInventoryItem.Field()