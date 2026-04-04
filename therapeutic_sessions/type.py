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


# 1. Digital Resource
class DigitalResourceType(DjangoObjectType):
    class Meta:
        model = DigitalResource
        fields = ("id", "title", "type", "category", "url")

    # Opcional: Si quieres que el valor del ChoiceField sea más legible
    type_display = graphene.String()

    def resolve_type_display(self, info):
        return self.get_type_display()


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
            "session_resources", "session_inventory","session_status",
        )

    # Campos calculados o representaciones amigables
    session_type_display = graphene.String()
    payment_status_display = graphene.String()

    def resolve_session_type_display(self, info):
        return self.get_session_type_display()

    def resolve_payment_status_display(self, info):
        return self.get_payment_status_display()

# ─────────────────────────────────────────
# CICLOS (tipo virtual — no es un modelo)
# Un ciclo = grupo de sesiones con el mismo cycle_number para un paciente.
# Se construye en el resolver agrupando sesiones, no tiene tabla propia.
# ─────────────────────────────────────────

class CyclePaymentSummaryType(graphene.ObjectType):
    """Resumen de estados de pago de las sesiones del ciclo."""
    paid = graphene.Int(description="Sesiones pagadas")
    pending = graphene.Int(description="Sesiones pendientes de pago")
    exempt = graphene.Int(description="Sesiones exentas de pago")


class CycleType(graphene.ObjectType):
    patient_id = graphene.ID()
    patient_name = graphene.String()
    cycle_number = graphene.Int()
    session_count = graphene.Int(description="Total de sesiones en el ciclo")
    first_session_date = graphene.DateTime(description="Fecha de la primera sesión del ciclo")
    last_session_date = graphene.DateTime(description="Fecha de la última sesión del ciclo")
    therapists = graphene.List(UserType, description="Terapeutas que atendieron en este ciclo")
    payment_summary = graphene.Field(CyclePaymentSummaryType)
