import uuid

from django.db import models
from users.models import User
from clinical.models import Patient
from institutions.models import InstitutionGroup


class DigitalResource(models.Model):

    class ResourceType(models.TextChoices):
        AUDIO = "audio", "Audio"
        VIDEO = "video", "Video"
        IMAGE = "image", "Imagen"
        SHEET_MUSIC = "sheet_music", "Partitura"
        DOCUMENT = "document", "Documento"
        WEB_LINK = "web_link", "Enlace web"

    title = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=ResourceType.choices)
    category = models.CharField(max_length=100, blank=True, null=True)
    url = models.URLField()

    class Meta:
        db_table = "digital_resources"

    def __str__(self):
        return f"{self.title} ({self.get_type_display()})"

class InventoryItem(models.Model):

    class ItemType(models.TextChoices):
        INSTRUMENT = "instrument", "Instrumento"
        EQUIPMENT = "equipment", "Equipo"
        MATERIAL = "material", "Material"

    class Condition(models.TextChoices):
        GOOD = "good", "Bueno"
        FAIR = "fair", "Regular"
        DAMAGED = "damaged", "Dañado"

    class Status(models.TextChoices):
        AVAILABLE = "available", "Disponible"
        IN_USE = "in_use", "En uso"
        MAINTENANCE = "maintenance", "En mantenimiento"

    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=ItemType.choices)
    condition = models.CharField(max_length=20, choices=Condition.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    room = models.CharField(max_length=255)

    class Meta:
        db_table = "inventory_items"

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

class Session(models.Model):

    class SessionType(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        GROUP = "group", "Grupal"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pendiente"
        PAID = "paid", "Pagada"
        EXEMPT = "exempt", "Exenta"

    class SessionStatus(models.TextChoices):
        COMPLETADA = "completa", "Completa"
        CONFIRMADA = "confirma", "Confirma"
        REPROGRAMA = "reprograma", "Reprograma"
        CANCELADA = "cancelada", "Cancelada"

    patient = models.ForeignKey(
        Patient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="therapeutic_sessions")
    therapist = models.ForeignKey(User, on_delete=models.PROTECT, related_name="therapeutic_sessions")
    group = models.ForeignKey(
        InstitutionGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="therapeutic_sessions",
    )

    session_date = models.DateTimeField()
    session_type = models.CharField(max_length=20, choices=SessionType.choices)
    session_status = models.CharField(max_length=20, choices=SessionStatus.choices, default=SessionStatus.COMPLETADA)
    session_number = models.IntegerField(default=0)
    duration_minutes = models.PositiveIntegerField(blank=True, null=True)
    cycle_number = models.PositiveIntegerField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    video_url = models.URLField(blank=True, null=True)
    #audio_url = models.URLField(blank=True, null=True)
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "therapeutic_sessions"
        ordering = ["-session_date"]

    def __str__(self):
        return f"Sesión {self.patient} — {self.session_date.date()}"

class SessionResource(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="session_resources")
    resource = models.ForeignKey(DigitalResource, on_delete=models.PROTECT, related_name="session_resources")

    class Meta:
        db_table = "session_resources"
        unique_together = [("session", "resource")]

    def __str__(self):
        return f"{self.resource} en {self.session}"

class SessionInventory(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="session_inventory")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="session_inventory")

    class Meta:
        db_table = "session_inventory"
        unique_together = [("session", "item")]

    def __str__(self):
        return f"{self.item} en {self.session}"