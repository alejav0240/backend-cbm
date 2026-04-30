from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from .models import (
    Course,
    CourseEnrollment,
    CoursePayment,
    Discount,
    Expense,
    Payment,
)


# ─────────────────────────────────────────
# Descuentos
# ─────────────────────────────────────────

@admin.register(Discount)
class DiscountAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = ("name", "display_type", "value", "description")
    list_filter = ("type",)
    search_fields = ("name",)
    ordering = ("name",)

    fieldsets = (
        (
            "Descuento",
            {"fields": ("name", "type", "value", "description")},
        ),
    )

    @display(
        description="Tipo",
        label={
            "percentage": "info",
            "fixed": "success",
        },
    )
    def display_type(self, obj):
        return obj.get_type_display()


# ─────────────────────────────────────────
# Pagos de sesiones
# ─────────────────────────────────────────

@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    change_list_template = "admin/custom_change_list.html"
    compressed_fields = True
    warn_unsaved_form = True
    list_fullwidth = True
    list_filter_submit = True

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        from django.db.models import Sum
        total_recuperado = Payment.objects.aggregate(Sum("amount_paid"))["amount_paid__sum"] or 0
        pendientes = Payment.objects.filter(payment_status="pending").count()
        
        extra_context["kpis"] = [
            {"label": "Recaudación Total", "value": f"Bs. {total_recuperado:,.2f}", "icon": "payments", "color": "success"},
            {"label": "Pagos Pendientes", "value": pendientes, "icon": "money_off", "color": "danger"},
            {"label": "Becas/Descuentos", "value": Payment.objects.filter(discount__isnull=False).count(), "icon": "redeem", "color": "warning"},
            {"label": "Total Transacciones", "value": Payment.objects.count(), "icon": "history", "color": "primary"},
        ]
        return super().changelist_view(request, extra_context=extra_context)

    list_display = (
        "patient",
        "sessions_count",
        "price_per_session",
        "amount_paid",
        "display_debt",
        "discount",
        "payment_method",
        "display_status",
        "payment_date",
    )
    list_filter = ("payment_status", "payment_method")
    search_fields = ("patient__first_name", "patient__last_name")
    ordering = ("-payment_date",)
    readonly_fields = ("payment_date", "created_at", "updated_at", "display_debt_readonly")
    autocomplete_fields = ("patient", "discount")

    fieldsets = (
        (
            "Paciente y descuento",
            {"fields": ("patient", "discount")},
        ),
        (
            "Detalle del pago",
            {
                "fields": (
                    ("sessions_count", "price_per_session"),
                    ("amount_paid", "display_debt_readonly"),
                    ("payment_method", "payment_status"),
                    "payment_date",
                )
            },
        ),
        (
            "Auditoría",
            {"fields": ("created_at", "updated_at")},
        ),
    )

    @display(description="Deuda calculada")
    def display_debt(self, obj):
        debt = obj.debt
        return f"{debt:.2f} Bs" if debt > 0 else "—"

    @display(description="Deuda")
    def display_debt_readonly(self, obj):
        return f"{obj.debt:.2f} Bs"

    @display(
        description="Estado",
        label={
            "pending": "warning",
            "partial": "info",
            "completed": "success",
        },
    )
    def display_status(self, obj):
        return obj.get_payment_status_display()

    actions = ("mark_completed",)

    @admin.action(description="Marcar como completados")
    def mark_completed(self, request, queryset):
        queryset.update(payment_status="completed")


# ─────────────────────────────────────────
# Gastos
# ─────────────────────────────────────────

@admin.register(Expense)
class ExpenseAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True

    list_display = (
        "description_preview",
        "category",
        "amount",
        "expense_date",
        "display_status",
    )
    list_filter = ("status", "category")
    search_fields = ("description", "category")
    ordering = ("-expense_date",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "Gasto",
            {"fields": ("description", "category", "amount", "expense_date")},
        ),
        (
            "Estado",
            {"fields": ("status", "created_at", "updated_at")},
        ),
    )

    @display(description="Descripción")
    def description_preview(self, obj):
        return obj.description[:80] + "..." if len(obj.description) > 80 else obj.description

    @display(
        description="Estado",
        label={
            "pending": "warning",
            "paid": "success",
            "cancelled": "danger",
        },
    )
    def display_status(self, obj):
        return obj.get_status_display()


# ─────────────────────────────────────────
# Cursos
# ─────────────────────────────────────────

class CourseEnrollmentInline(TabularInline):
    model = CourseEnrollment
    extra = 0
    fields = ("full_name", "carnet", "enrolled_at")
    readonly_fields = ("enrolled_at",)
    show_change_link = True


@admin.register(Course)
class CourseAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = ("name", "price", "display_state", "enrollment_count")
    list_filter = ("state",)
    search_fields = ("name",)
    ordering = ("name",)
    inlines = (CourseEnrollmentInline,)

    fieldsets = (
        (
            "Curso",
            {"fields": ("name", "description", "price", "state")},
        ),
    )

    @display(
        description="Estado",
        label={
            "draft": "warning",
            "active": "success",
            "archived": "info",
        },
    )
    def display_state(self, obj):
        return obj.get_state_display()

    def enrollment_count(self, obj):
        return obj.enrollments.count()

    enrollment_count.short_description = "Inscritos"


class CoursePaymentInline(TabularInline):
    model = CoursePayment
    max_num = 1
    extra = 0
    fields = ("payment_method", "amount", "payment_status", "payment_date")
    readonly_fields = ("payment_date",)


@admin.register(CourseEnrollment)
class CourseEnrollmentAdmin(ModelAdmin):
    compressed_fields = True
    list_filter_submit = True

    list_display = (
        "full_name",
        "course",
        "carnet",
        "enrolled_at",
        "display_payment_status",
    )
    list_filter = ("course",)
    search_fields = ("full_name", "carnet", "course__name")
    ordering = ("-enrolled_at",)
    readonly_fields = ("enrolled_at",)
    autocomplete_fields = ("course",)
    inlines = (CoursePaymentInline,)

    fieldsets = (
        (
            "Inscripción",
            {
                "fields": (
                    ("course"),
                    ("full_name", "carnet"),
                    "enrolled_at",
                )
            },
        ),
    )

    @display(
        description="Pago",
        label={
            "pending": "warning",
            "completed": "success",
            "refunded": "info",
            None: "danger",
        },
    )
    def display_payment_status(self, obj):
        try:
            return obj.payment.get_payment_status_display()
        except CoursePayment.DoesNotExist:
            return "Sin pago"