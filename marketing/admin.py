from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from .models import Lead, MarketingCampaign


class LeadInline(TabularInline):
    model = Lead
    extra = 0
    fields = ("name", "email", "phone", "status")
    show_change_link = True


@admin.register(MarketingCampaign)
class MarketingCampaignAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_fullwidth = True
    list_filter_submit = True

    list_display = (
        "name",
        "platform",
        "display_status",
        "budget",
        "spent",
        "display_remaining",
        "lead_count",
    )
    list_filter = ("status", "platform")
    search_fields = ("name", "platform")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    inlines = (LeadInline,)

    fieldsets = (
        (
            "Campaña",
            {"fields": ("name", "platform", "status")},
        ),
        (
            "Presupuesto",
            {"fields": ("budget", "spent")},
        ),
        (
            "Auditoría",
            {"fields": ("created_at", "updated_at")},
        ),
    )

    @display(
        description="Estado",
        label={
            "draft": "warning",
            "active": "success",
            "paused": "info",
            "finished": "danger",
        },
    )
    def display_status(self, obj):
        return obj.get_status_display()

    @display(description="Restante")
    def display_remaining(self, obj):
        remaining = obj.remaining_budget
        prefix = "+" if remaining >= 0 else ""
        return f"{prefix}{remaining:.2f} Bs"

    def lead_count(self, obj):
        return obj.leads.count()

    lead_count.short_description = "Leads"

    actions = ("pause_campaigns", "finish_campaigns")

    @admin.action(description="Pausar campañas seleccionadas")
    def pause_campaigns(self, request, queryset):
        queryset.filter(status="active").update(status="paused")

    @admin.action(description="Finalizar campañas seleccionadas")
    def finish_campaigns(self, request, queryset):
        queryset.update(status="finished")


@admin.register(Lead)
class LeadAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_fullwidth = True
    list_filter_submit = True

    list_display = (
        "name",
        "email",
        "phone",
        "display_status",
        "campaign",
        "created_at",
    )
    list_filter = ("status", "campaign")
    search_fields = ("name", "email", "phone")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("campaign",)

    fieldsets = (
        (
            "Datos del lead",
            {"fields": ("name", "email", "phone")},
        ),
        (
            "CRM",
            {"fields": ("status", "campaign")},
        ),
        (
            "Auditoría",
            {"fields": ("created_at", "updated_at")},
        ),
    )

    @display(
        description="Estado",
        label={
            "new": "info",
            "contacted": "warning",
            "qualified": "success",
            "lost": "danger",
        },
    )
    def display_status(self, obj):
        return obj.get_status_display()

    actions = ("mark_contacted", "mark_qualified", "mark_lost")

    @admin.action(description="Marcar como contactados")
    def mark_contacted(self, request, queryset):
        queryset.update(status="contacted")

    @admin.action(description="Marcar como calificados")
    def mark_qualified(self, request, queryset):
        queryset.update(status="qualified")

    @admin.action(description="Marcar como perdidos")
    def mark_lost(self, request, queryset):
        queryset.update(status="lost")