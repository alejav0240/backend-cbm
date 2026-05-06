import graphene
from graphene_django import DjangoObjectType

from clinical.models import Patient, PatientClinicalNote, InterventionPlan, PlanStep, TherapyReport


class PatientType(DjangoObjectType):
    full_name = graphene.String()
    database_id = graphene.Int()

    class Meta:
        model = Patient
        fields = (
            "id", "tutor","database_id",
            "first_name", "last_name",
            "ci", "birth_date",
            "image_url", "notes", "status",
            "created_at", "updated_at",
            "clinical_notes", "intervention_plans",
            "therapy_reports", "therapeutic_sessions",
            "scale_evaluations", "payments",
            "registration_complete","diagnosis","residence",
        )

        interfaces = (graphene.relay.Node,)

    def resolve_database_id(self, info):
        return self.pk

    def resolve_full_name(self, info):
        return f"{self.first_name} {self.last_name}"


class PatientClinicalNoteType(DjangoObjectType):
    class Meta:
        model = PatientClinicalNote
        fields = ("id", "patient", "author", "category", "content", "created_at")


class InterventionPlanType(DjangoObjectType):
    status = graphene.String()

    class Meta:
        model = InterventionPlan
        fields = (
            "id", "patient", "created_by",
            "main_objective", "start_date", "end_date",
            "progress_percent", "created_at", "updated_at",
            "steps",
        )

    def resolve_status(self, info):
        if self.progress_percent == 100:
            return "Finalizado"
        return "En curso"


class PlanStepType(DjangoObjectType):
    class Meta:
        model = PlanStep
        fields = (
            "id", "plan", "moment", "duration_minutes", "actual_duration",
            "objective", "focus", "musical_resources",
            "musical_emphasis", "approach", "mlt_method",
            "order_index", "is_completed",
        )


class TherapyReportType(DjangoObjectType):
    class Meta:
        model = TherapyReport
        fields = ("id", "patient", "generated_by", "report_url", "created_at")

class GrowthPointType(graphene.ObjectType):
    month = graphene.String()
    total = graphene.Int()