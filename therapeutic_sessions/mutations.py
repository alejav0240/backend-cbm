import math
import graphene
import base64
from graphql import GraphQLError
from django.db.models.functions import Coalesce

from therapeutic_sessions.models import Session, SessionResource, SessionInventory, InventoryItem, DigitalResource
from therapeutic_sessions.type import SessionType, DigitalResourceType, InventoryItemType, CycleType, PaginatedDigitalResources
from config.utils import get_db_id, module_permission_required

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

    @module_permission_required('sesiones', action='add')
    def mutate(self, info, patient_id=None, therapist_id=None, session_date=None, session_type=None,
               duration_minutes=None, notes=None, group_id=None, video_url=None):
        
        db_patient_id = get_db_id(patient_id)
        db_therapist_id = get_db_id(therapist_id)
        db_group_id = get_db_id(group_id)

        if not db_therapist_id:
            raise GraphQLError("ID de terapeuta inválido o no proporcionado.")

        current_session_number = 0
        if db_patient_id:
            last_session_data = Session.objects.filter(patient_id=db_patient_id).aggregate(
                last_num=Coalesce(Max('session_number'), 0)
            )
            current_session_number = last_session_data['last_num'] + 1

        calculated_cycle = math.ceil(current_session_number / 4) if current_session_number > 0 else 0

        session = Session.objects.create(
            patient_id=db_patient_id,
            therapist_id=db_therapist_id,
            session_date=session_date,
            session_type=session_type,
            session_status=Session.SessionStatus.AGENDADA,
            session_number=current_session_number,
            cycle_number=calculated_cycle,
            duration_minutes=duration_minutes,
            notes=notes,

            group_id=db_group_id,
            video_url=video_url,
        )

        return CreateSession(session=session)


class UpdateSession(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        notes = graphene.String()
        duration_minutes = graphene.Int()
        video_url = graphene.String()
        session_status = graphene.String()
        therapist_id = graphene.ID()
        session_date = graphene.DateTime()
        session_type = graphene.String()

    session = graphene.Field(SessionType)

    @module_permission_required('sesiones', action='change')
    def mutate(self, info, id, notes=None, duration_minutes=None, video_url=None,
               session_status=None, therapist_id=None, session_date=None, session_type=None):
        real_id = get_db_id(id)
        try:
            session = Session.objects.get(pk=real_id)
            if notes is not None:
                session.notes = notes
            if duration_minutes is not None:
                session.duration_minutes = duration_minutes
            if video_url is not None:
                session.video_url = video_url
            if session_status is not None:
                session.session_status = session_status
            if therapist_id is not None:
                session.therapist_id = get_db_id(therapist_id)
            if session_date is not None:
                session.session_date = session_date
            if session_type is not None:
                session.session_type = session_type
            session.save()
            return UpdateSession(session=session)
        except Session.DoesNotExist:
            raise GraphQLError("Sesión no encontrada")


class UpdateSessionPaymentStatus(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        payment_status = graphene.String(required=True)

    session = graphene.Field(SessionType)

    @module_permission_required('sesiones', action='change')
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

    session_resource = graphene.Boolean()

    @module_permission_required('sesiones', action='change')
    def mutate(self, info, session_id, resource_id):
        db_session_id = get_db_id(session_id)
        db_resource_id = get_db_id(resource_id)

        SessionResource.objects.get_or_create(
            session_id=db_session_id, resource_id=db_resource_id
        )
        return AddSessionResource(session_resource=True)


class AddSessionInventoryItem(graphene.Mutation):
    class Arguments:
        session_id = graphene.ID(required=True)
        item_id = graphene.ID(required=True)

    session_inventory = graphene.Field(SessionType)

    @module_permission_required('sesiones', action='change')
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

    @module_permission_required('inventario', action='add')
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

    @module_permission_required('inventario', action='change')
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

    @module_permission_required('inventario', action='delete')
    def mutate(self, info, id):
        db_id = get_db_id(id)
        try:
            item = InventoryItem.objects.get(pk=db_id)
            item.delete()
            return DeleteInventoryItem(success=True)
        except InventoryItem.DoesNotExist:
            return DeleteInventoryItem(success=False)

class CreateDigitalResource(graphene.Mutation):
    class Arguments:
        title = graphene.String(required=True)
        type = graphene.String(required=True)
        category = graphene.String()
        url = graphene.String(required=True)

    resource = graphene.Field(DigitalResourceType)

    @module_permission_required('recursos', action='add')
    def mutate(self, info, title, type, url, category=None):
        resource = DigitalResource.objects.create(
            title=title,
            type=type,
            url=url,
            category=category
        )
        return CreateDigitalResource(resource=resource)

class UpdateDigitalResource(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        title = graphene.String()
        type = graphene.String()
        category = graphene.String()
        url = graphene.String()

    resource = graphene.Field(DigitalResourceType)

    @module_permission_required('recursos', action='change')
    def mutate(self, info, id, **kwargs):
        db_id = get_db_id(id)
        try:
            resource = DigitalResource.objects.get(pk=db_id)
            for key, value in kwargs.items():
                setattr(resource, key, value)
            resource.save()
            return UpdateDigitalResource(resource=resource)
        except DigitalResource.DoesNotExist:
            raise GraphQLError("Recurso no encontrado")

class DeleteDigitalResource(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    success = graphene.Boolean()

    @module_permission_required('recursos', action='delete')
    def mutate(self, info, id):
        db_id = get_db_id(id)
        try:
            resource = DigitalResource.objects.get(pk=db_id)
            resource.delete()
            return DeleteDigitalResource(success=True)
        except DigitalResource.DoesNotExist:
            return DeleteDigitalResource(success=False)

class CreateCycle(graphene.Mutation):
    class Arguments:
        patient_id = graphene.ID(required=True)
        therapist_id = graphene.ID(required=True)
        start_date = graphene.Date(required=True)
        num_sessions = graphene.Int(default_value=4)

    success = graphene.Boolean()
    message = graphene.String()

    @module_permission_required('sesiones', action='add')
    def mutate(self, info, patient_id, therapist_id, start_date, num_sessions=4):
        db_patient_id = get_db_id(patient_id)
        db_therapist_id = get_db_id(therapist_id)

        if not db_patient_id:
            raise GraphQLError("ID de paciente inválido.")
        if not db_therapist_id:
            raise GraphQLError("ID de terapeuta inválido.")

        last_session = Session.objects.filter(patient_id=db_patient_id).aggregate(
            last_num=Coalesce(Max('session_number'), 0)
        )
        current_num = last_session['last_num']

        from datetime import timedelta
        
        sessions_to_create = []
        for i in range(num_sessions):
            current_num += 1
            calculated_cycle = math.ceil(current_num / 4)
            session_date = start_date + timedelta(weeks=i)
            
            sessions_to_create.append(
                Session(
                    patient_id=db_patient_id,
                    therapist_id=db_therapist_id,
                    session_date=session_date,
                    session_type="individual",
                    session_number=current_num,
                    cycle_number=calculated_cycle,
                    session_status="agendada",
                    payment_status="pending"
                )
            )
        
        Session.objects.bulk_create(sessions_to_create)
        return CreateCycle(success=True, message=f"Se han creado {num_sessions} sesiones exitosamente.")

class DeleteSession(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    @module_permission_required('sesiones', action='delete')
    def mutate(self, info, id):
        real_id = get_db_id(id)
        try:
            session = Session.objects.get(pk=real_id)
            session.delete()
            return DeleteSession(success=True, message="Sesión eliminada correctamente")
        except Session.DoesNotExist:
            return DeleteSession(success=False, message="La sesión no existe")
        except Exception as e:
            return DeleteSession(success=False, message=str(e))


class Mutation(graphene.ObjectType):
    create_session = CreateSession.Field()
    create_cycle = CreateCycle.Field()
    update_session = UpdateSession.Field()
    update_session_payment_status = UpdateSessionPaymentStatus.Field()
    add_session_resource = AddSessionResource.Field()
    add_session_inventory_item = AddSessionInventoryItem.Field()
    create_inventory_item = CreateInventoryItem.Field()
    update_inventory_item = UpdateInventoryItem.Field()
    delete_inventory_item = DeleteInventoryItem.Field()
    create_digital_resource = CreateDigitalResource.Field()
    update_digital_resource = UpdateDigitalResource.Field()
    delete_digital_resource = DeleteDigitalResource.Field()
    delete_session = DeleteSession.Field()
