from django.contrib import admin
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.decorators import display

from .models import (
    InterventionPlan,
    Patient,
    PatientClinicalNote,
    PlanStep,
    TherapyReport,
)


class PatientClinicalNoteInline(StackedInline):
    model = PatientClinicalNote
    extra = 0
    fields = ("category", "author", "content", "created_at")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
    show_change_link = True


class InterventionPlanInline(TabularInline):
    model = InterventionPlan
    extra = 0
    fields = ("main_objective", "start_date", "end_date", "progress_percent")
    show_change_link = True


class TherapyReportInline(TabularInline):
    model = TherapyReport
    extra = 0
    fields = ("generated_by", "report_url", "created_at")
    readonly_fields = ("created_at",)
    show_change_link = False


class PlanStepInline(TabularInline):
    model = PlanStep
    extra = 0
    fields = (
        "order_index",
        "moment",
        "duration_minutes",
        "objective",
        "mlt_method",
    )
    ordering = ("order_index",)


@admin.register(Patient)
class PatientAdmin(ModelAdmin):
    change_list_template = "admin/custom_change_list.html"
    compressed_fields = True
    warn_unsaved_form = True
    list_fullwidth = True
    list_filter_submit = True

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        total = Patient.objects.count()
        active = Patient.objects.filter(status="active").count()
        discharged = Patient.objects.filter(status="discharged").count()
        
        extra_context["kpis"] = [
            {"label": "Total Pacientes", "value": total, "icon": "person", "color": "primary"},
            {"label": "Activos", "value": active, "icon": "how_to_reg", "color": "success"},
            {"label": "Dada de Alta", "value": discharged, "icon": "task_alt", "color": "info"},
            {"label": "Planes Activos", "value": InterventionPlan.objects.count(), "icon": "assignment", "color": "warning"},
        ]
        return super().changelist_view(request, extra_context=extra_context)

    list_display = (
        "id",
        "full_name",
        "ci",
        "birth_date",
        "tutor",
        "display_status",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("first_name", "last_name", "ci")
    ordering = ("last_name", "first_name")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("tutor",)
    inlines = (
        PatientClinicalNoteInline,
        InterventionPlanInline,
        TherapyReportInline,
    )

    fieldsets = (
        (
            "Datos del paciente",
            {
                "fields": (
                    ("first_name", "last_name"),
                    ("ci", "birth_date"),
                    "image_url",
                )
            },
        ),
        (
            "Tutor",
            {"fields": ("tutor",)},
        ),
        (
            "Estado",
            {
                "fields": (
                    ("status", "notes"),
                    ("created_at", "updated_at"),
                )
            },
        ),
    )

    @display(description="Nombre completo")
    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"

    @display(
        description="Estado",
        label={
            "active": "success",
            "inactive": "warning",
            "discharged": "info",
        },
    )
    def display_status(self, obj):
        return obj.get_status_display()


@admin.register(PatientClinicalNote)
class PatientClinicalNoteAdmin(ModelAdmin):
    compressed_fields = True
    list_filter_submit = True

    list_display = ("patient", "display_category", "author", "content_preview", "created_at")
    list_filter = ("category",)
    search_fields = ("patient__first_name", "patient__last_name", "content")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    autocomplete_fields = ("patient", "author")

    fieldsets = (
        (
            "Nota clínica",
            {"fields": ("patient", "author", "category", "content", "created_at")},
        ),
    )

    @display(description="Contenido")
    def content_preview(self, obj):
        return obj.content[:100] + "..." if len(obj.content) > 100 else obj.content

    @display(
        description="Categoría",
        label={
            "diagnosis": "danger",
            "general_objective": "info",
            "observation": "warning",
        },
    )
    def display_category(self, obj):
        return obj.get_category_display()


@admin.register(InterventionPlan)
class InterventionPlanAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True

    list_display = (
        "patient",
        "main_objective_preview",
        "start_date",
        "end_date",
        "display_progress",
        "created_by",
    )
    search_fields = ("patient__first_name", "patient__last_name", "main_objective")
    ordering = ("-start_date",)
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("patient", "created_by")
    inlines = (PlanStepInline,)

    fieldsets = (
        (
            "Plan",
            {
                "fields": (
                    "patient",
                    "created_by",
                    "main_objective",
                )
            },
        ),
        (
            "Fechas y progreso",
            {
                "fields": (
                    ("start_date", "end_date"),
                    "progress_percent",
                    ("created_at", "updated_at"),
                )
            },
        ),
    )

    @display(description="Objetivo")
    def main_objective_preview(self, obj):
        return obj.main_objective[:80] + "..." if len(obj.main_objective) > 80 else obj.main_objective

    @display(description="Progreso")
    def display_progress(self, obj):
        return f"{obj.progress_percent}%"


@admin.register(TherapyReport)
class TherapyReportAdmin(ModelAdmin):
    compressed_fields = True

    list_display = ("patient", "generated_by", "report_url", "created_at")
    search_fields = ("patient__first_name", "patient__last_name")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    autocomplete_fields = ("patient", "generated_by")

    fieldsets = (
        (
            "Reporte",
            {"fields": ("patient", "generated_by", "report_url", "created_at")},
        ),
    )