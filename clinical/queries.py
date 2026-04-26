from django.utils import timezone
import graphene
from graphql import GraphQLError
from dateutil.relativedelta import relativedelta
from django.db.models import Count
from django.db.models.functions import TruncMonth

from .models import Patient, PatientClinicalNote, InterventionPlan, TherapyReport
from .type import PatientType, PatientClinicalNoteType, InterventionPlanType, TherapyReportType, GrowthPointType


class PaginatedPatients(graphene.ObjectType):
    results = graphene.List(PatientType)
    total_count = graphene.Int()
    total_pages = graphene.Int()
    current_page = graphene.Int()

class Query(graphene.ObjectType):
    patients = graphene.Field(
        PaginatedPatients,
        status=graphene.String(),
        search=graphene.String(),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
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

    patient_growth = graphene.List(GrowthPointType)

    def resolve_patients(self, info, status=None, search=None, page=1, page_size=10):
        qs = Patient.objects.select_related("tutor").all()
        if status:
            qs = qs.filter(status=status)
        if search:
            qs = qs.filter(first_name__icontains=search) \
                 | qs.filter(last_name__icontains=search) \
                 | qs.filter(ci__icontains=search)

        # Sort the queryset based on the sorted_by parameter
        # Forzar orden descendente manualmente
        qs = qs.order_by('-created_at')

        total_count = qs.count()
        total_pages = (total_count + page_size - 1) // page_size
        offset = (page - 1) * page_size
        results = qs[offset:offset + page_size]

        return PaginatedPatients(
            results=results,
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )

    def resolve_patient(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        try:
            return Patient.objects.select_related("tutor").get(pk=real_id)
        except Patient.DoesNotExist:
            raise GraphQLError("Paciente no encontrado")

    def resolve_clinical_notes(self, info, patient_id, category=None):
        try:
            real_patient_id = int(graphene.relay.Node.from_global_id(patient_id)[1])
        except:
            real_patient_id = patient_id
        qs = PatientClinicalNote.objects.filter(patient_id=real_patient_id).select_related("author")
        if category:
            qs = qs.filter(category=category)
        return qs

    def resolve_intervention_plans(self, info, patient_id):
        try:
            real_patient_id = int(graphene.relay.Node.from_global_id(patient_id)[1])
        except:
            real_patient_id = patient_id
        return InterventionPlan.objects.filter(patient_id=real_patient_id).prefetch_related("steps")

    def resolve_intervention_plan(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        try:
            return InterventionPlan.objects.prefetch_related("steps").get(pk=real_id)
        except InterventionPlan.DoesNotExist:
            raise GraphQLError("Plan de intervención no encontrado")

    def resolve_therapy_reports(self, info, patient_id):
        try:
            real_patient_id = int(graphene.relay.Node.from_global_id(patient_id)[1])
        except:
            real_patient_id = patient_id
        return TherapyReport.objects.filter(patient_id=real_patient_id).select_related("generated_by")

    def resolve_patient_growth(self, info):
        # Generamos los últimos 6 meses con valor 0 por defecto
        last_6_months = {}
        for i in range(5, -1, -1):
            month_dt = timezone.now() - relativedelta(months=i)
            last_6_months[month_dt.strftime('%b')] = 0

        # Consultamos la DB
        data = (
            Patient.objects.filter(created_at__gte=timezone.now() - relativedelta(months=6))
            .annotate(month_date=TruncMonth('created_at'))
            .values('month_date')
            .annotate(total=Count('id'))
        )

        # Llenamos los datos reales sobre los ceros
        for item in data:
            month_name = item['month_date'].strftime('%b')
            if month_name in last_6_months:
                last_6_months[month_name] = item['total']

        return [GrowthPointType(month=m, total=t) for m, t in last_6_months.items()]
