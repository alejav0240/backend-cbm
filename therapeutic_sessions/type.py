import graphene
from graphene_django import DjangoObjectType
from therapeutic_sessions.models import (
    DigitalResource,
    InventoryItem,
    Session,
    SessionResource,
    SessionInventory
)
from users.types import UserType
from clinical.type import PatientType
from evaluations.type import ScaleEvaluationType, FormAssignmentType


# 1. Digital Resource
class DigitalResourceType(DjangoObjectType):
    class Meta:
        model = DigitalResource
        fields = ("id", "title", "type", "category", "url")

    # Opcional: Si quieres que el valor del ChoiceField sea más legible
    type_display = graphene.String()

    def resolve_type_display(self, info):
        return self.get_type_display()

class PaginatedDigitalResources(graphene.ObjectType):
    results = graphene.List(DigitalResourceType)
    total_count = graphene.Int()
    total_pages = graphene.Int()
    current_page = graphene.Int()


class PaginatedSessions(graphene.ObjectType):
    """
    Resultado paginado de sesiones.
    - Paginación normal (by_cycles=False): `sessions` contiene los datos.
    - Paginación por ciclos (by_cycles=True): `cycles` contiene los datos y `sessions` es null.
    """
    sessions = graphene.List(lambda: SessionType)
    cycles = graphene.List(lambda: CycleType)
    total_count = graphene.Int()
    total_pages = graphene.Int()
    current_page = graphene.Int()
    by_cycles = graphene.Boolean(description="Indica si la respuesta está paginada por ciclos.")


class PaginatedCycles(graphene.ObjectType):
    """Paginación por ciclos: cada página contiene ciclos completos."""
    results = graphene.List(lambda: CycleType)
    total_count = graphene.Int()
    total_pages = graphene.Int()
    current_page = graphene.Int()


# 2. Inventory Item
class InventoryItemType(DjangoObjectType):
    class Meta:
        model = InventoryItem
        fields = ("id", "name", "type", "condition", "status", "room")

    status_display = graphene.String()

    def resolve_status_display(self, info):
        return self.get_status_display()


# 3. Session Resource (Relación intermedia)
class SessionResourceType(DjangoObjectType):
    class Meta:
        model = SessionResource
        fields = ("id", "session", "resource")


# 4. Session Inventory (Relación intermedia)
class SessionInventoryType(DjangoObjectType):
    class Meta:
        model = SessionInventory
        fields = ("id", "session", "item")


# 5. Session (El nodo principal)
class SessionType(DjangoObjectType):
    class Meta:
        model = Session
        fields = (
            "id", "patient", "therapist", "group",
            "session_date", "session_type",
            "duration_minutes", "cycle_number",
            "notes", "video_url",
            "payment_status", "created_at", "updated_at",
            "session_resources", "session_inventory",
            "session_status", "session_number",
            "scale_evaluations", "session_plan_steps",
        )
        interfaces = (graphene.relay.Node,)

    # Campo para obtener el ID real de la DB si se necesita en el front
    database_id = graphene.Int()

    def resolve_database_id(self, info):
        return self.pk

    # Campos calculados o representaciones amigables
    session_type_display = graphene.String()
    payment_status_display = graphene.String()
    # Formularios del paciente relacionados con esta sesión (via patient FK)
    form_assignments = graphene.List(
        FormAssignmentType,
        description="Asignaciones de formularios del paciente vinculado a esta sesión.",
    )

    def resolve_session_type_display(self, info):
        return self.get_session_type_display()

    def resolve_payment_status_display(self, info):
        return self.get_payment_status_display()

    def resolve_form_assignments(self, info):
        if not self.patient_id:
            return []
        from evaluations.models import FormAssignment
        return FormAssignment.objects.filter(patient_id=self.patient_id).select_related(
            "form", "assigned_to", "assigned_by"
        ).prefetch_related("responses")

# ─────────────────────────────────────────
# CICLOS (tipo virtual — no es un modelo)
# Un ciclo = grupo de sesiones con el mismo cycle_number para un paciente.
# Se construye en el resolver agrupando sesiones, no tiene tabla propia.
# ─────────────────────────────────────────

class PaginatedPatientsLastCycle(graphene.ObjectType):
    """Paginación de últimos ciclos por paciente."""
    results = graphene.List(lambda: CycleType)
    total_count = graphene.Int()
    total_pages = graphene.Int()
    current_page = graphene.Int()


class CyclePaymentSummaryType(graphene.ObjectType):
    """Resumen de estados de pago de las sesiones del ciclo."""
    paid = graphene.Int(description="Sesiones pagadas")
    pending = graphene.Int(description="Sesiones pendientes de pago")
    exempt = graphene.Int(description="Sesiones exentas de pago")


class CycleType(graphene.ObjectType):
    id = graphene.ID(description="ID único virtual del ciclo")
    patient_id = graphene.ID()
    patient_db_id = graphene.Int()
    patient = graphene.Field(PatientType)
    patient_name = graphene.String()
    cycle_number = graphene.Int()
    session_count = graphene.Int(description="Total de sesiones en el ciclo")
    completed_count = graphene.Int(description="Sesiones completadas en el ciclo")
    status = graphene.String(description="Estado del ciclo (Activo/Finalizado)")
    sessions = graphene.List(SessionType, description="Sesiones que pertenecen a este ciclo")
    first_session_date = graphene.DateTime(description="Fecha de la primera sesión del ciclo")
    last_session_date = graphene.DateTime(description="Fecha de la última sesión del ciclo")
    therapists = graphene.List(UserType, description="Terapeutas que atendieron en este ciclo")
    payment_summary = graphene.Field(CyclePaymentSummaryType)
