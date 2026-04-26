import graphene
from graphql import GraphQLError

from therapeutic_sessions.models import DigitalResource, Session, InventoryItem
from therapeutic_sessions.type import SessionType, DigitalResourceType, InventoryItemType, CycleType


# ═══════════════════════════════════════════════════════════════
# HELPER — agrupación de ciclos
# Un ciclo = conjunto de sesiones con el mismo (patient_id, cycle_number).
# Se construye en Python sobre un queryset ya filtrado para evitar
# múltiples queries: 1 query de sesiones → agrupación en memoria.
# ═══════════════════════════════════════════════════════════════

def _build_cycles(base_qs):
    """
    Recibe un queryset de Session con cycle_number__isnull=False.
    Devuelve una lista de CycleType ordenada por patient y cycle_number.
    """
    from collections import defaultdict
    from .type import CyclePaymentSummaryType, CycleType

    sessions = (
        base_qs
        .select_related("patient", "therapist")
        .order_by("patient_id", "cycle_number", "session_date")
    )

    if not sessions.exists():
        return []

    # Agrupa en memoria: clave = (patient_id, cycle_number)
    groups = defaultdict(list)
    for s in sessions:
        if s.cycle_number:
            groups[(s.patient_id, s.cycle_number)].append(s)

    cycles = []
    for (patient_id, cycle_number), sess_list in sorted(groups.items()):
        first = sess_list[0]
        last = sess_list[-1]

        # Terapeutas únicos del ciclo (preserva orden de aparición)
        seen_therapist_ids = set()
        therapists = []
        for s in sess_list:
            if s.therapist_id not in seen_therapist_ids:
                seen_therapist_ids.add(s.therapist_id)
                therapists.append(s.therapist)

        # Resumen de pagos
        paid = sum(1 for s in sess_list if s.payment_status == "paid")
        pending = sum(1 for s in sess_list if s.payment_status == "pending")
        exempt = sum(1 for s in sess_list if s.payment_status == "exempt")

        cycles.append(
            CycleType(
                patient_id=patient_id,
                patient_name=f"{first.patient.first_name} {first.patient.last_name}",
                cycle_number=cycle_number,
                session_count=len(sess_list),
                first_session_date=first.session_date,
                last_session_date=last.session_date,
                therapists=therapists,
                payment_summary=CyclePaymentSummaryType(
                    paid=paid,
                    pending=pending,
                    exempt=exempt,
                ),
            )
        )
    return cycles


class Query(graphene.ObjectType):
    sessions = graphene.List(
        SessionType,
        patient_id=graphene.ID(),
        therapist_id=graphene.ID(),
        session_type=graphene.String(),
        payment_status=graphene.String(),
        session_status=graphene.String(),
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

    # Ciclos de un paciente específico
    patient_cycles = graphene.List(
        CycleType,
        patient_id=graphene.ID(required=True),
        description="Ciclos de sesiones de un paciente, agrupados por cycle_number.",
    )

    # Ciclos de todos los pacientes activos
    all_patient_cycles = graphene.List(
        CycleType,
        description="Ciclos de todos los pacientes, ordenados por paciente y cycle_number.",
    )

    def resolve_sessions(self, info, patient_id=None, therapist_id=None,
                         session_type=None, payment_status=None, session_status=None,):
        qs = Session.objects.select_related("patient", "therapist", "group").all()
        if patient_id:
            try:
                real_patient_id = int(graphene.relay.Node.from_global_id(patient_id)[1])
            except:
                real_patient_id = patient_id
            qs = qs.filter(patient_id=real_patient_id)
        if therapist_id:
            try:
                real_therapist_id = int(graphene.relay.Node.from_global_id(therapist_id)[1])
            except:
                real_therapist_id = therapist_id
            qs = qs.filter(therapist_id=real_therapist_id)
        if session_type:
            qs = qs.filter(session_type=session_type)
        if payment_status:
            qs = qs.filter(payment_status=payment_status)
        if session_status:
            qs = qs.filter(session_status=session_status) # FIX: Corregido de session_type a session_status
        return qs

    def resolve_session(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        try:
            return Session.objects.select_related(
                "patient", "therapist", "group"
            ).prefetch_related(
                "session_resources__resource",
                "session_inventory__item",
                # "scale_evaluations", # Comentado si el campo no existe en el modelo para evitar fallos
            ).get(pk=real_id)
        except Session.DoesNotExist:
            raise GraphQLError("Sesión no encontrada")

    def resolve_digital_resources(self, info, type=None, search=None):
        qs = DigitalResource.objects.all()
        if type:
            qs = qs.filter(type=type)
        if search:
            qs = qs.filter(title__icontains=search)
        return qs

    def resolve_digital_resource(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        try:
            return DigitalResource.objects.get(pk=real_id)
        except DigitalResource.DoesNotExist:
            raise GraphQLError("Recurso digital no encontrado")

    def resolve_inventory_items(self, info, status=None, type=None):
        qs = InventoryItem.objects.all()
        if status:
            qs = qs.filter(status=status)
        if type:
            qs = qs.filter(type=type)
        return qs

    def resolve_inventory_item(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        try:
            return InventoryItem.objects.get(pk=real_id)
        except InventoryItem.DoesNotExist:
            raise GraphQLError("Item de inventario no encontrado")

    def resolve_patient_cycles(self, info, patient_id):
        try:
            real_patient_id = int(graphene.relay.Node.from_global_id(patient_id)[1])
        except:
            real_patient_id = patient_id
        qs = Session.objects.filter(patient_id=real_patient_id, cycle_number__isnull=False)
        return _build_cycles(qs)

    def resolve_all_patient_cycles(self, info):
        qs = Session.objects.filter(cycle_number__isnull=False)
        return _build_cycles(qs)
