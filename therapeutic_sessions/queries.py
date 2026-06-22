import graphene
from graphql import GraphQLError

from therapeutic_sessions.models import DigitalResource, Session, InventoryItem
from therapeutic_sessions.type import (
    SessionType, DigitalResourceType, InventoryItemType, CycleType,
    PaginatedDigitalResources, PaginatedSessions, PaginatedCycles,
    PaginatedPatientsLastCycle,
)
from config.utils import get_db_id, module_permission_required


# ═══════════════════════════════════════════════════════════════
# HELPER — agrupación de ciclos
# Un ciclo = conjunto de sesiones con el mismo (patient_id, cycle_number).
# Se construye en Python sobre un queryset ya filtrado para evitar
# múltiples queries: 1 query de sesiones → agrupación en memoria.
# ═══════════════════════════════════════════════════════════════

def _build_cycles(base_qs):
    """
    Recibe un queryset de Session con cycle_number__isnull=False.
    Devuelve una lista de CycleType ordenada de más reciente a más antiguo
    (descendente por cycle_number). Página 1 = ciclo más reciente.
    """
    from collections import defaultdict
    from .type import CyclePaymentSummaryType, CycleType
    import base64

    sessions = (
        base_qs
        .select_related("patient", "therapist")
        .prefetch_related(
            "session_resources__resource",
            "session_inventory__item",
            "scale_evaluations__scale",
            "scale_evaluations__evaluator",
            "scale_evaluations__subscale_responses__subscale",
            "scale_evaluations__value_responses__scale_value",
        )
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

        # Conteo de completitud
        completed = sum(1 for s in sess_list if s.session_status.lower() == "completa")

        # Estado del ciclo
        status = "Finalizado" if completed == len(sess_list) else "Activo"

        # Generar un ID único virtual para Apollo (Base64 de P:ID-C:NUM)
        virtual_id_raw = f"Patient:{patient_id}-Cycle:{cycle_number}"
        virtual_id = base64.b64encode(virtual_id_raw.encode()).decode()

        cycles.append(
            CycleType(
                id=virtual_id,
                patient_id=graphene.relay.Node.to_global_id("PatientType", patient_id),
                patient_db_id=patient_id,
                patient=first.patient,
                patient_name=f"{first.patient.first_name} {first.patient.last_name}",
                cycle_number=cycle_number,
                session_count=len(sess_list),
                completed_count=completed,
                status=status,
                sessions=sess_list,
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

    # Más reciente primero: ciclo con mayor cycle_number = página 1
    cycles.sort(key=lambda c: c.cycle_number, reverse=True)
    return cycles


class Query(graphene.ObjectType):
    sessions = graphene.Field(
        PaginatedSessions,
        patient_id=graphene.ID(),
        therapist_id=graphene.ID(),
        session_type=graphene.String(),
        payment_status=graphene.String(),
        session_status=graphene.String(),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
        by_cycles=graphene.Boolean(
            default_value=False,
            description="False → paginación normal de sesiones. True → paginación por ciclos (devuelve PaginatedCycles).",
        ),
    )
    paginated_cycles = graphene.Field(
        PaginatedCycles,
        patient_id=graphene.ID(),
        therapist_id=graphene.ID(),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
        description="Paginación por ciclos. Disponible también desde `sessions(byCycles: true)`.",
    )
    session = graphene.Field(SessionType, id=graphene.ID(required=True))

    digital_resources = graphene.Field(
        PaginatedDigitalResources,
        type=graphene.String(),
        search=graphene.String(),
        page=graphene.Int(),
        page_size=graphene.Int(),
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

    # Último ciclo activo por paciente (uno por paciente)
    patients_last_cycle = graphene.Field(
        PaginatedPatientsLastCycle,
        therapist_id=graphene.ID(),
        search=graphene.String(description="Busca por nombre o apellido del paciente."),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
        description="Lista paginada de pacientes con la información de su último ciclo y sus sesiones.",
    )

    @module_permission_required('sesiones', action='view')
    def resolve_sessions(self, info, patient_id=None, therapist_id=None,
                         session_type=None, payment_status=None, session_status=None,
                         page=1, page_size=10, by_cycles=False):
        qs = Session.objects.select_related("patient", "therapist", "group").all()
        if patient_id:
            qs = qs.filter(patient_id=get_db_id(patient_id))
        if therapist_id:
            qs = qs.filter(therapist_id=get_db_id(therapist_id))
        if session_type:
            qs = qs.filter(session_type=session_type)
        if payment_status:
            qs = qs.filter(payment_status=payment_status)
        if session_status:
            qs = qs.filter(session_status=session_status)

        if by_cycles:
            # ── Paginación por ciclos: 1 ciclo por página, página 1 = más reciente ──
            cycles_qs = qs.filter(cycle_number__isnull=False)
            all_cycles = _build_cycles(cycles_qs)
            total_count = len(all_cycles)
            total_pages = total_count  # cada ciclo es una página
            offset = page - 1         # page_size=1 fijo
            page_cycles = all_cycles[offset:offset + 1]
            return PaginatedSessions(
                sessions=None,
                cycles=page_cycles,
                total_count=total_count,
                total_pages=total_pages,
                current_page=page,
                by_cycles=True,
            )

        # ── Paginación normal ──────────────────────────────────────────────
        total_count = qs.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        offset = (page - 1) * page_size
        return PaginatedSessions(
            sessions=list(qs[offset:offset + page_size]),
            cycles=None,
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
            by_cycles=False,
        )

    @module_permission_required('sesiones', action='view')
    def resolve_paginated_cycles(self, info, patient_id=None, therapist_id=None,
                                 page=1, page_size=10):
        qs = Session.objects.select_related("patient", "therapist", "group").filter(
            cycle_number__isnull=False
        )
        if patient_id:
            qs = qs.filter(patient_id=get_db_id(patient_id))
        if therapist_id:
            qs = qs.filter(therapist_id=get_db_id(therapist_id))

        all_cycles = _build_cycles(qs)
        total_count = len(all_cycles)
        total_pages = total_count  # cada ciclo es una página
        offset = page - 1         # page_size=1 fijo
        page_cycles = all_cycles[offset:offset + 1]

        return PaginatedCycles(
            results=page_cycles,
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )

    @module_permission_required('sesiones', action='view')
    def resolve_session(self, info, id):
        real_id = get_db_id(id)
        try:
            return Session.objects.select_related(
                "patient", "therapist", "group"
            ).prefetch_related(
                "session_resources__resource",
                "session_inventory__item",
                "scale_evaluations__scale",
                "scale_evaluations__evaluator",
                "scale_evaluations__subscale_responses__subscale",
                "scale_evaluations__value_responses__scale_value",
            ).get(pk=real_id)
        except Session.DoesNotExist:
            raise GraphQLError("Sesión no encontrada")

    @module_permission_required('recursos', action='view')
    def resolve_digital_resources(self, info, type=None, search=None, page=1, page_size=10):
        qs = DigitalResource.objects.all()
        if type:
            qs = qs.filter(type=type)
        if search:
            qs = qs.filter(title__icontains=search)
            
        total_count = qs.count()
        total_pages = (total_count + page_size - 1) // page_size
        offset = (page - 1) * page_size
        results = qs[offset:offset + page_size]

        return PaginatedDigitalResources(
            results=results,
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )

    @module_permission_required('recursos', action='view')
    def resolve_digital_resource(self, info, id):
        real_id = get_db_id(id)
        try:
            return DigitalResource.objects.get(pk=real_id)
        except DigitalResource.DoesNotExist:
            raise GraphQLError("Recurso digital no encontrado")

    @module_permission_required('inventario', action='view')
    def resolve_inventory_items(self, info, status=None, type=None):
        qs = InventoryItem.objects.all()
        if status:
            qs = qs.filter(status=status)
        if type:
            qs = qs.filter(type=type)
        return qs

    @module_permission_required('inventario', action='view')
    def resolve_inventory_item(self, info, id):
        real_id = get_db_id(id)
        try:
            return InventoryItem.objects.get(pk=real_id)
        except InventoryItem.DoesNotExist:
            raise GraphQLError("Item de inventario no encontrado")

    def resolve_patient_cycles(self, info, patient_id):
        real_patient_id = get_db_id(patient_id)
        qs = Session.objects.filter(patient_id=real_patient_id, cycle_number__isnull=False)
        return _build_cycles(qs)

    def resolve_all_patient_cycles(self, info):
        qs = Session.objects.filter(cycle_number__isnull=False)
        return _build_cycles(qs)

    @module_permission_required('sesiones', action='view')
    def resolve_patients_last_cycle(self, info, therapist_id=None, search=None, page=1, page_size=10):
        """
        Para cada paciente, devuelve únicamente su ciclo más reciente
        (mayor cycle_number) junto con las sesiones que lo componen.
        Soporta búsqueda por nombre/apellido y paginación.
        """
        from django.db.models import Max, Q

        qs = Session.objects.filter(cycle_number__isnull=False)
        if therapist_id:
            qs = qs.filter(therapist_id=get_db_id(therapist_id))

        # Filtro de búsqueda por nombre/apellido del paciente
        if search:
            qs = qs.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search)
            )

        # Obtener el cycle_number máximo por paciente en una sola query
        max_cycles = list(
            qs.values("patient_id")
            .annotate(last_cycle=Max("cycle_number"))
        )

        if not max_cycles:
            return PaginatedPatientsLastCycle(
                results=[], total_count=0, total_pages=0, current_page=page
            )

        # Construir filtro: (patient_id=X AND cycle_number=Y) OR ...
        query = Q()
        for row in max_cycles:
            query |= Q(patient_id=row["patient_id"], cycle_number=row["last_cycle"])

        last_cycle_sessions = Session.objects.filter(query)
        all_cycles = _build_cycles(last_cycle_sessions)

        # Ordenar alfabéticamente por nombre de paciente
        all_cycles.sort(key=lambda c: c.patient_name or "")

        # Paginación en memoria (la agrupación ya se hizo sobre los datos filtrados)
        total_count = len(all_cycles)
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        offset = (page - 1) * page_size
        page_results = all_cycles[offset:offset + page_size]

        return PaginatedPatientsLastCycle(
            results=page_results,
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )
