from django.contrib import admin
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.decorators import display

from .models import (
    Form,
    FormAssignment,
    FormQuestion,
    FormResponse,
    Scale,
    ScaleEvaluation,
    ScaleEvaluationSubscaleResponse,
    ScaleEvaluationValueResponse,
    ScaleValue,
    Subscale,
)


# ─────────────────────────────────────────
# Escalas
# ─────────────────────────────────────────

class SubscaleInline(TabularInline):
    model = Subscale
    extra = 1
    fields = ("name", "description", "max_value")


class ScaleValueInline(TabularInline):
    model = ScaleValue
    extra = 1
    fields = ("label", "value")
    ordering = ("value",)


@admin.register(Scale)
class ScaleAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = ("name", "display_type")
    list_filter = ("scale_type",)
    search_fields = ("name",)
    ordering = ("name",)
    inlines = (SubscaleInline, ScaleValueInline)

    fieldsets = (
        (
            "Escala",
            {"fields": ("name", "description", "scale_type")},
        ),
    )

    @display(
        description="Tipo",
        label={
            "subscale": "info",
            "value_list": "success",
        },
    )
    def display_type(self, obj):
        return obj.get_scale_type_display()


# ─────────────────────────────────────────
# Evaluaciones
# ─────────────────────────────────────────

class ScaleEvaluationSubscaleResponseInline(TabularInline):
    model = ScaleEvaluationSubscaleResponse
    extra = 0
    fields = ("subscale", "score")
    autocomplete_fields = ("subscale",)


class ScaleEvaluationValueResponseInline(TabularInline):
    model = ScaleEvaluationValueResponse
    extra = 0
    fields = ("scale_value",)
    autocomplete_fields = ("scale_value",)

@admin.register(Subscale)
class SubscaleAdmin(ModelAdmin):
    search_fields = ("name",)  # Obligatorio para que autocomplete funcione

@admin.register(ScaleValue)
class ScaleValueAdmin(ModelAdmin):
    search_fields = ("label",)  # O el campo que quieras usar para buscar

@admin.register(ScaleEvaluation)
class ScaleEvaluationAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_fullwidth = True
    list_filter_submit = True

    list_display = (
        "patient",
        "scale",
        "evaluator",
        "display_context",
        "evaluated_at",
    )
    list_filter = ("scale", "evaluator")
    search_fields = (
        "patient__first_name",
        "patient__last_name",
        "scale__name",
        "evaluator__first_name",
        "evaluator__last_name",
    )
    ordering = ("-evaluated_at",)
    readonly_fields = ("evaluated_at",)
    autocomplete_fields = ("scale", "patient", "evaluator", )
    inlines = (
        ScaleEvaluationSubscaleResponseInline,
        ScaleEvaluationValueResponseInline,
    )

    fieldsets = (
        (
            "Evaluación",
            {
                "fields": (
                    ("patient", "scale"),
                    ("evaluator", "evaluated_at"),
                    "session",
                    "notes",
                )
            },
        ),
    )

    @display(
        description="Contexto",
        label={True: "info", False: "success"},
    )
    def display_context(self, obj):
        return "En sesión" if obj.session_id else "Fuera de sesión"


# ─────────────────────────────────────────
# Formularios
# ─────────────────────────────────────────

class FormQuestionInline(StackedInline):
    model = FormQuestion
    extra = 1
    fields = ("order_index", "question", "question_type", "is_required")
    ordering = ("order_index",)


class FormResponseInline(TabularInline):
    model = FormResponse
    extra = 0
    fields = ("question", "response", "responded_at")
    readonly_fields = ("question", "responded_at")
    can_delete = False


@admin.register(Form)
class FormAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = ("name", "question_count")
    search_fields = ("name",)
    ordering = ("name",)
    inlines = (FormQuestionInline,)

    fieldsets = (
        (
            "Formulario",
            {"fields": ("name", "description")},
        ),
    )

    def question_count(self, obj):
        return obj.questions.count()

    question_count.short_description = "Preguntas"


@admin.register(FormAssignment)
class FormAssignmentAdmin(ModelAdmin):
    compressed_fields = True
    list_filter_submit = True

    list_display = (
        "form",
        "assigned_to",
        "assigned_by",
        "patient",
        "display_completion",
        "created_at",
    )
    list_filter = ("form",)
    search_fields = (
        "form__name",
        "assigned_to__username",
        "patient__first_name",
        "patient__last_name",
    )
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    autocomplete_fields = ("form", "assigned_to", "assigned_by", "patient")
    inlines = (FormResponseInline,)

    fieldsets = (
        (
            "Asignación",
            {
                "fields": (
                    ("form", "patient"),
                    ("assigned_to", "assigned_by"),
                    "created_at",
                )
            },
        ),
    )

    @display(description="Respuestas")
    def display_completion(self, obj):
        total = obj.form.questions.count()
        answered = obj.responses.count()
        return f"{answered}/{total}"