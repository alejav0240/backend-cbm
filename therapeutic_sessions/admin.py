from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from .models import (
    DigitalResource,
    InventoryItem,
    Session,
    SessionInventory,
    SessionResource,
)


class SessionResourceInline(TabularInline):
    model = SessionResource
    extra = 0
    fields = ("resource",)
    autocomplete_fields = ("resource",)


class SessionInventoryInline(TabularInline):
    model = SessionInventory
    extra = 0
    fields = ("item",)
    autocomplete_fields = ("item",)

@admin.register(DigitalResource)
class DigitalResourceAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = ("title", "display_type", "category", "url")
    list_filter = ("type", "category")
    search_fields = ("title", "category")
    ordering = ("type", "title")

    fieldsets = (
        (
            "Recurso",
            {"fields": ("title", "type", "category", "url")},
        ),
    )

    @display(
        description="Tipo",
        label={
            "audio": "success",
            "video": "info",
            "sheet_music": "warning",
            "document": "danger",
        },
    )
    def display_type(self, obj):
        return obj.get_type_display()


@admin.register(InventoryItem)
class InventoryItemAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True

    list_display = ("name", "display_type", "display_condition", "display_status")
    list_filter = ("type", "condition", "status")
    search_fields = ("name",)
    ordering = ("type", "name")

    fieldsets = (
        (
            "Ítem",
            {"fields": ("name", "type")},
        ),
        (
            "Estado",
            {"fields": ("condition", "status")},
        ),
    )

    @display(
        description="Tipo",
        label={
            "instrument": "success",
            "equipment": "info",
            "material": "warning",
        },
    )
    def display_type(self, obj):
        return obj.get_type_display()

    @display(
        description="Condición",
        label={
            "good": "success",
            "fair": "warning",
            "damaged": "danger",
        },
    )
    def display_condition(self, obj):
        return obj.get_condition_display()

    @display(
        description="Disponibilidad",
        label={
            "available": "success",
            "in_use": "info",
            "maintenance": "warning",
        },
    )
    def display_status(self, obj):
        return obj.get_status_display()

    actions = ("mark_available", "mark_maintenance")

    @admin.action(description="Marcar como disponibles")
    def mark_available(self, request, queryset):
        queryset.update(status="available")

    @admin.action(description="Marcar en mantenimiento")
    def mark_maintenance(self, request, queryset):
        queryset.update(status="maintenance")


@admin.register(Session)
class SessionAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_fullwidth = True
    list_filter_submit = True

    list_display = (
        "patient",
        "therapist",
        "session_date",
        "display_type",
        "duration_minutes",
        "cycle_number",
        "display_payment_status",
    )
    list_filter = ("session_type", "payment_status", "therapist")
    search_fields = (
        "patient__first_name",
        "patient__last_name",
        "therapist__first_name",
        "therapist__last_name",
    )
    ordering = ("-session_date",)
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("patient", "therapist", "group")
    inlines = (SessionResourceInline, SessionInventoryInline)

    fieldsets = (
        (
            "Sesión",
            {
                "fields": (
                    ("patient", "therapist"),
                    ("session_date", "session_type"),
                    ("duration_minutes", "cycle_number"),
                    ("group","session_status")
                )
            },
        ),
        (
            "Multimedia y notas",
            {
                "fields": (
                    "notes",
                    ("video_url"),
                )
            },
        ),
        (
            "Pago y auditoría",
            {
                "fields": (
                    "payment_status",
                    ("created_at", "updated_at"),
                )
            },
        ),
    )

    @display(
        description="Tipo",
        label={
            "individual": "info",
            "group": "success",
        },
    )
    def display_type(self, obj):
        return obj.get_session_type_display()

    @display(
        description="Pago",
        label={
            "pending": "warning",
            "paid": "success",
            "exempt": "info",
        },
    )
    def display_payment_status(self, obj):
        return obj.get_payment_status_display()

    actions = ("mark_paid", "mark_exempt")

    @admin.action(description="Marcar como pagadas")
    def mark_paid(self, request, queryset):
        queryset.update(payment_status="paid")

    @admin.action(description="Marcar como exentas")
    def mark_exempt(self, request, queryset):
        queryset.update(payment_status="exempt")
