import graphene

from .models import Patient, PatientClinicalNote, InterventionPlan, TherapyReport
from .type import PatientType, PatientClinicalNoteType, InterventionPlanType, TherapyReportType


class Query(graphene.ObjectType):
    patients = graphene.List(
        PatientType,
        status=graphene.String(),
        search=graphene.String(),
    )
    patient = graphene.Field(PatientType, id=graphene.ID(required=True))

    clinical_notes = graphene.List(
        PatientClinicalNoteType,
        patient_id=graphene.ID(required=True),
        category=graphene.String(),
    )

    intervention_plans = graphene.List(
        InterventionPlanType,
        patient_id=graphene.ID(required=True),
    )
    intervention_plan = graphene.Field(InterventionPlanType, id=graphene.ID(required=True))

    therapy_reports = graphene.List(
        TherapyReportType,
        patient_id=graphene.ID(required=True),
    )

    def resolve_patients(self, info, status=None, search=None):
        qs = Patient.objects.select_related("tutor").all()
        if status:
            qs = qs.filter(status=status)
        if search:
            qs = qs.filter(
                first_name__icontains=search
            ) | qs.filter(
                last_name__icontains=search
            ) | qs.filter(
                ci__icontains=search
            )
        return qs

    def resolve_patient(self, info, id):
        return Patient.objects.select_related("tutor").get(pk=id)

    def resolve_clinical_notes(self, info, patient_id, category=None):
        qs = PatientClinicalNote.objects.filter(patient_id=patient_id).select_related("author")
        if category:
            qs = qs.filter(category=category)
        return qs

    def resolve_intervention_plans(self, info, patient_id):
        return InterventionPlan.objects.filter(patient_id=patient_id).prefetch_related("steps")

    def resolve_intervention_plan(self, info, id):
        return InterventionPlan.objects.prefetch_related("steps").get(pk=id)

    def resolve_therapy_reports(self, info, patient_id):
        return TherapyReport.objects.filter(patient_id=patient_id).select_related("generated_by")
