from django.db import models
from clinical.models import Patient
from users.models import User


class Discount(models.Model):

    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "Porcentaje"
        FIXED = "fixed", "Monto fijo"

    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=DiscountType.choices)
    value = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = "discounts"

    def __str__(self):
        suffix = "%" if self.type == self.DiscountType.PERCENTAGE else " Bs"
        return f"{self.name} ({self.value}{suffix})"


class Payment(models.Model):
    """
    Cubre un paquete de N sesiones.
    Deuda = (price_per_session × sessions_count) - amount_paid
    La deuda es un campo derivado — no se persiste.
    """

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Efectivo"
        TRANSFER = "transfer", "Transferencia"
        CARD = "card", "Tarjeta"
        QR = "qr", "QR"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pendiente"
        PARTIAL = "partial", "Parcial"
        COMPLETED = "completed", "Completado"

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="payments")
    discount = models.ForeignKey(
        Discount, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments"
    )
    sessions_count = models.PositiveIntegerField()
    price_per_session = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    payment_date = models.DateTimeField(auto_now_add=True)
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payments"
        ordering = ["-payment_date"]

    @property
    def total_amount(self):
        if self.price_per_session and self.sessions_count:
            return self.price_per_session * self.sessions_count
        return 0

    @property
    def debt(self):
        if self.amount_paid is not None:
            return self.total_amount - self.amount_paid
        return self.total_amount

    def __str__(self):
        return f"Pago {self.patient} — {self.payment_date.date()} ({self.get_payment_status_display()})"


class Expense(models.Model):

    class ExpenseStatus(models.TextChoices):
        PENDING = "pending", "Pendiente"
        PAID = "paid", "Pagado"
        CANCELLED = "cancelled", "Cancelado"

    description = models.TextField()
    category = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    expense_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=ExpenseStatus.choices, default=ExpenseStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "expenses"
        ordering = ["-expense_date"]

    def __str__(self):
        return f"{self.category} — {self.amount} ({self.expense_date.date()})"


# ─────────────────────────────────────────
# Cursos (inscripción + pago)
# ─────────────────────────────────────────

class Course(models.Model):

    class CourseState(models.TextChoices):
        DRAFT = "draft", "Borrador"
        ACTIVE = "active", "Activo"
        ARCHIVED = "archived", "Archivado"

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    state = models.CharField(max_length=20, choices=CourseState.choices, default=CourseState.DRAFT)

    class Meta:
        db_table = "courses"

    def __str__(self):
        return f"{self.name} ({self.get_state_display()})"


class CourseEnrollment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="enrollments")
    # user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="enrollments")
    full_name = models.CharField(max_length=255)
    carnet = models.CharField(max_length=50, blank=True, null=True)
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "course_enrollments"
        unique_together = [("course", "full_name")]

    def __str__(self):
        return f"{self.full_name} → {self.course}"


class CoursePayment(models.Model):

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Efectivo"
        TRANSFER = "transfer", "Transferencia"
        CARD = "card", "Tarjeta"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pendiente"
        COMPLETED = "completed", "Completado"
        REFUNDED = "refunded", "Reembolsado"

    enrollment = models.OneToOneField(
        CourseEnrollment, on_delete=models.CASCADE, related_name="payment"
    )
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )

    class Meta:
        db_table = "course_payments"

    def __str__(self):
        return f"Pago de {self.enrollment} ({self.get_payment_status_display()})"