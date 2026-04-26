import math
import graphene
import base64
from graphql import GraphQLError
from django.db.models.functions import Coalesce

from therapeutic_sessions.models import Session, SessionResource, SessionInventory, InventoryItem
from therapeutic_sessions.type import SessionType, SessionResourceType, SessionInventoryType, InventoryItemType

from django.db.models import Max

def get_db_id(global_id):
    """
    Helper para obtener el ID real de la DB desde un ID de Relay o un ID plano.
    """
    if not global_id:
        return None
    
    # Si ya es un número o string numérico directo
    if isinstance(global_id, int):
        return global_id
    if isinstance(global_id, str) and global_id.isdigit():
        return int(global_id)
    
    # Intentar decodificar Relay Global ID (Base64)
    try:
        # Añadir padding si falta (común en transmisiones base64)
        if isinstance(global_id, str):
            padding = len(global_id) % 4
            if padding:
                global_id += "=" * (4 - padding)
            
            decoded = base64.b64decode(global_id).decode('utf-8')
            if ':' in decoded:
                # El formato de Relay es "TypeName:InternalID"
                return int(decoded.split(':')[1])
    except Exception:
        pass
        
    return None

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

    def mutate(self, info, patient_id=None, therapist_id=None, session_date=None, session_type=None,
               duration_minutes=None, notes=None, group_id=None, video_url=None):
        
        db_patient_id = get_db_id(patient_id)
        db_therapist_id = get_db_id(therapist_id)
        db_group_id = get_db_id(group_id)

        if not db_therapist_id:
            raise GraphQLError("ID de terapeuta inválido o no proporcionado.")

        # 1. Calcular el número de sesión correlativo para este paciente
        current_session_number = 0
        if db_patient_id:
            last_session_data = Session.objects.filter(patient_id=db_patient_id).aggregate(
                last_num=Coalesce(Max('session_number'), 0)
            )
            current_session_number = last_session_data['last_num'] + 1

        # 2. Calcular el ciclo (cada 4 sesiones es un ciclo)
        calculated_cycle = math.ceil(current_session_number / 4) if current_session_number > 0 else 0

        # 3. Crear la sesión con los IDs numéricos reales
        session = Session.objects.create(
            patient_id=db_patient_id,
            therapist_id=db_therapist_id,
            session_date=session_date,
            session_type=session_type,
            session_number=current_session_number,
            cycle_number=calculated_cycle,
            duration_minutes=duration_minutes,
            notes=notes,
            group_id=db_group_id,
            video_url=video_url,
        )

        return CreateSession(session=session)


class UpdateSessionPaymentStatus(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        payment_status = graphene.String(required=True)

    session = graphene.Field(SessionType)

    def mutate(self, info, id, payment_status):
        real_id = get_db_id(id)
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
        db_session_id = get_db_id(session_id)
        db_resource_id = get_db_id(resource_id)

        sr, _ = SessionResource.objects.get_or_create(
            session_id=db_session_id, resource_id=db_resource_id
        )
        return AddSessionResource(session_resource=sr)


class AddSessionInventoryItem(graphene.Mutation):
    class Arguments:
        session_id = graphene.ID(required=True)
        item_id = graphene.ID(required=True)

    session_inventory = graphene.Field(SessionInventoryType)

    def mutate(self, info, session_id, item_id):
        db_session_id = get_db_id(session_id)
        db_item_id = get_db_id(item_id)

        si, _ = SessionInventory.objects.get_or_create(
            session_id=db_session_id, item_id=db_item_id
        )
        return AddSessionInventoryItem(session_inventory=si)

class CreateInventoryItem(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        type = graphene.String(required=True)
        condition = graphene.String(required=True)
        status = graphene.String()
        room = graphene.String(required=True)

    item = graphene.Field(InventoryItemType)

    def mutate(self, info, name, type, condition, room, status="available"):
        item = InventoryItem.objects.create(
            name=name,
            type=type,
            condition=condition,
            status=status,
            room=room
        )
        return CreateInventoryItem(item=item)

class UpdateInventoryItem(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        name = graphene.String()
        type = graphene.String()
        condition = graphene.String()
        status = graphene.String()
        room = graphene.String()

    item = graphene.Field(InventoryItemType)

    def mutate(self, info, id, **kwargs):
        db_id = get_db_id(id)
        try:
            item = InventoryItem.objects.get(pk=db_id)
            for key, value in kwargs.items():
                setattr(item, key, value)
            item.save()
            return UpdateInventoryItem(item=item)
        except InventoryItem.DoesNotExist:
            raise GraphQLError("Item no encontrado")

class DeleteInventoryItem(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    success = graphene.Boolean()

    def mutate(self, info, id):
        db_id = get_db_id(id)
        try:
            item = InventoryItem.objects.get(pk=db_id)
            item.delete()
            return DeleteInventoryItem(success=True)
        except InventoryItem.DoesNotExist:
            return DeleteInventoryItem(success=False)

class Mutation(graphene.ObjectType):
    create_session = CreateSession.Field()
    update_session_payment_status = UpdateSessionPaymentStatus.Field()
    add_session_resource = AddSessionResource.Field()
    add_session_inventory_item = AddSessionInventoryItem.Field()
    create_inventory_item = CreateInventoryItem.Field()
    update_inventory_item = UpdateInventoryItem.Field()
    delete_inventory_item = DeleteInventoryItem.Field()
