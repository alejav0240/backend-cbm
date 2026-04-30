from django.db import models
from users.models import User
from clinical.models import Patient


# ─────────────────────────────────────────
# Definición de escalas
# ─────────────────────────────────────────

class Scale(models.Model):

    class ScaleType(models.TextChoices):
        SUBSCALE = "subscale", "Por subescalas"
        VALUE_LIST = "value_list", "Por lista de valores"

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    scale_type = models.CharField(max_length=20, choices=ScaleType.choices)

    class Meta:
        db_table = "scales"

    def __str__(self):
        return f"{self.name} ({self.get_scale_type_display()})"


class Subscale(models.Model):
    scale = models.ForeignKey(Scale, on_delete=models.CASCADE, related_name="subscales")
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=255, blank=True, null=True)
    max_value = models.PositiveIntegerField()

    class Meta:
        db_table = "subscales"

    def __str__(self):
        return f"{self.name} (max: {self.max_value}) — {self.scale}"


class ScaleValue(models.Model):
    scale = models.ForeignKey(Scale, on_delete=models.CASCADE, related_name="values")
    label = models.CharField(max_length=255)
    value = models.IntegerField()

    class Meta:
        db_table = "scale_values"
        ordering = ["value"]

    def __str__(self):
        return f"{self.label} ({self.value}) — {self.scale}"


# ─────────────────────────────────────────
# Aplicación de escalas
# ─────────────────────────────────────────

class ScaleEvaluation(models.Model):
    """
    Una instancia de evaluar a un paciente con una escala.
    session puede ser null si la evaluación es fuera de sesión.
    """
    scale = models.ForeignKey(Scale, on_delete=models.PROTECT, related_name="evaluations")
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="scale_evaluations")
    evaluator = models.ForeignKey(User, on_delete=models.PROTECT, related_name="scale_evaluations")
    # Import diferido para evitar circular import con therapeutic_sessions
    session = models.ForeignKey(
        "therapeutic_sessions.Session",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scale_evaluations",
    )
    evaluated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "scale_evaluations"
        ordering = ["-evaluated_at"]

    @property
    def total_score(self):
        if self.scale.scale_type == Scale.ScaleType.SUBSCALE:
            return sum(r.score for r in self.subscale_responses.all())
        elif self.scale.scale_type == Scale.ScaleType.VALUE_LIST:
            return sum(r.scale_value.value for r in self.value_responses.all())
        return 0

    def __str__(self):
        ctx = f"sesión {self.session_id}" if self.session_id else "fuera de sesión"
        return f"{self.scale} — {self.patient} ({ctx})"


class ScaleEvaluationSubscaleResponse(models.Model):
    """
    Respuesta para escalas de tipo 'subscale'.
    Un registro por cada subescala dentro de la evaluación.
    """
    evaluation = models.ForeignKey(
        ScaleEvaluation, on_delete=models.CASCADE, related_name="subscale_responses"
    )
    subscale = models.ForeignKey(Subscale, on_delete=models.PROTECT, related_name="responses")
    score = models.PositiveIntegerField()

    class Meta:
        db_table = "scale_evaluation_subscale_responses"
        unique_together = [("evaluation", "subscale")]

    def __str__(self):
        return f"{self.subscale.name}: {self.score} — {self.evaluation}"


class ScaleEvaluationValueResponse(models.Model):
    """
    Respuesta para escalas de tipo 'value_list'.
    Un registro por cada valor seleccionado dentro de la evaluación.
    """
    evaluation = models.ForeignKey(
        ScaleEvaluation, on_delete=models.CASCADE, related_name="value_responses"
    )
    scale_value = models.ForeignKey(ScaleValue, on_delete=models.PROTECT, related_name="responses")

    class Meta:
        db_table = "scale_evaluation_value_responses"
        unique_together = [("evaluation", "scale_value")]

    def __str__(self):
        return f"{self.scale_value.label} — {self.evaluation}"


# ─────────────────────────────────────────
# Formularios
# ─────────────────────────────────────────

class Form(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "forms"

    def __str__(self):
        return self.name


class FormQuestion(models.Model):

    class QuestionType(models.TextChoices):
        TEXT_LONG = "text_long", "Texto libre"
        TEXTAREA = "text", "Texto corto"
        NUMBER = "number", "Número"
        DATE = "date", "Fecha"
        BOOLEAN = "boolean", "Sí / No"
        SCALE = "scale", "Escala"
        MULTIPLE_CHOICE = "multiple_choice", "Opción múltiple"

    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="questions")
    question = models.TextField()
    question_type = models.CharField(max_length=20, choices=QuestionType.choices)
    is_required = models.BooleanField(default=True)
    order_index = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "form_questions"
        ordering = ["order_index"]

    def __str__(self):
        return f"{self.question[:80]} — {self.form}"


class FormAssignment(models.Model):
    form = models.ForeignKey(Form, on_delete=models.PROTECT, related_name="assignments")
    assigned_to = models.ForeignKey(User, on_delete=models.PROTECT, related_name="received_form_assignments")
    assigned_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="sent_form_assignments")
    patient = models.ForeignKey(
        Patient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="form_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "form_assignments"

    def __str__(self):
        return f"{self.form} → {self.assigned_to}"


class FormResponse(models.Model):
    assignment = models.ForeignKey(FormAssignment, on_delete=models.CASCADE, related_name="responses")
    question = models.ForeignKey(FormQuestion, on_delete=models.PROTECT, related_name="responses")
    response = models.TextField()
    responded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "form_responses"
        unique_together = [("assignment", "question")]

    def __str__(self):
        return f"Respuesta de {self.assignment.assigned_to} — {self.question.question[:60]}"