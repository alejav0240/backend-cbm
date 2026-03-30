from django.db import models
from users.models import User


class Patient(models.Model):

    class Status(models.TextChoices):
        ACTIVE = "active", "Activo"
        INACTIVE = "inactive", "Inactivo"
        DISCHARGED = "discharged", "Alta"

    tutor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tutored_patients",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    ci = models.CharField(max_length=30, blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)
    image_url = models.URLField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "patients"

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


# todo: es nesesario ?
class PatientClinicalNote(models.Model):

    class Category(models.TextChoices):
        DIAGNOSIS = "diagnosis", "Diagnóstico"
        GENERAL_OBJECTIVE = "general_objective", "Objetivo general"
        OBSERVATION = "observation", "Observación"

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="clinical_notes")
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="authored_notes")
    category = models.CharField(max_length=30, choices=Category.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "patient_clinical_notes"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_category_display()} — {self.patient} ({self.created_at.date()})"


class InterventionPlan(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="intervention_plans")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_plans")
    main_objective = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    progress_percent = models.PositiveSmallIntegerField(default=0)  # 0-100
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "intervention_plans"

    def __str__(self):
        return f"Plan de {self.patient} — {self.start_date}"


class PlanStep(models.Model):

    class Moment(models.TextChoices):
        INITIAL = "initial", "Inicio"
        DEVELOPMENT = "development", "Desarrollo"
        CLOSURE = "closure", "Cierre"

    plan = models.ForeignKey(InterventionPlan, on_delete=models.CASCADE, related_name="steps")
    moment = models.CharField(max_length=20, choices=Moment.choices)
    duration_minutes = models.PositiveIntegerField(blank=True, null=True)
    objective = models.CharField(max_length=255)
    focus = models.TextField(blank=True, null=True)
    musical_resources = models.TextField(blank=True, null=True)
    musical_emphasis = models.CharField(max_length=255, blank=True, null=True)
    approach = models.CharField(max_length=255, blank=True, null=True)
    mlt_method = models.CharField(max_length=100, blank=True, null=True)
    order_index = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "plan_steps"
        ordering = ["order_index"]

    def __str__(self):
        return f"{self.get_moment_display()} — {self.objective[:60]}"


class TherapyReport(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="therapy_reports")
    generated_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="generated_reports")
    report_url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "therapy_reports"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Reporte de {self.patient} ({self.created_at.date()})"