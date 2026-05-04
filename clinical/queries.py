from django.utils import timezone
import graphene
from graphql import GraphQLError
from dateutil.relativedelta import relativedelta
from django.db.models import Count
from django.db.models.functions import TruncMonth
import base64

from .models import Patient, PatientClinicalNote, InterventionPlan, TherapyReport
from .type import PatientType, PatientClinicalNoteType, InterventionPlanType, TherapyReportType, GrowthPointType

def get_real_id(id_attr):
    if not id_attr:
        return None
    
    # Si ya es un entero o parece serlo, no decodificamos
    if isinstance(id_attr, int) or (isinstance(id_attr, str) and id_attr.isdigit()):
        return id_attr
        
    try:
        # Intentar decodificación manual de Relay (Base64)
        # Relay IDs suelen ser "Tipo:ID" codificados en Base64
        decoded = base64.b64decode(str(id_attr)).decode('utf-8')
        if ":" in decoded:
            return decoded.split(":")[1]
        return decoded
    except Exception:
        # Si falla el Base64, intentar el helper de Graphene por si acaso
        try:
            from graphql_relay import from_global_id
            return from_global_id(id_attr)[1]
        except Exception:
            # Si todo falla, devolver el original
            return id_attr

class PaginatedPatients(graphene.ObjectType):
    results = graphene.List(PatientType)
    total_count = graphene.Int()
    total_pages = graphene.Int()
    current_page = graphene.Int()

class PaginatedInterventionPlans(graphene.ObjectType):
    results = graphene.List(InterventionPlanType)
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

    intervention_plans = graphene.Field(
        PaginatedInterventionPlans,
        patient_id=graphene.ID(required=False),
        search=graphene.String(),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
    )
    intervention_plan = graphene.Field(InterventionPlanType, id=graphene.ID(required=True))

    therapy_reports = graphene.List(
        TherapyReportType,
        patient_id=graphene.ID(required=False),
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
        real_id = get_real_id(id)
        try:
            return Patient.objects.select_related("tutor").get(pk=real_id)
        except (Patient.DoesNotExist, ValueError, TypeError):
            raise GraphQLError(f"Paciente con ID {real_id} no encontrado")

    def resolve_clinical_notes(self, info, patient_id, category=None):
        real_patient_id = get_real_id(patient_id)
        qs = PatientClinicalNote.objects.filter(patient_id=real_patient_id).select_related("author")
        if category:
            qs = qs.filter(category=category)
        return qs

    def resolve_intervention_plans(self, info, patient_id=None, search=None, page=1, page_size=10):
        qs = InterventionPlan.objects.select_related("patient").prefetch_related("steps").all()
        if patient_id:
            real_patient_id = get_real_id(patient_id)
            qs = qs.filter(patient_id=real_patient_id)
        
        if search:
            qs = qs.filter(patient__first_name__icontains=search) \
                 | qs.filter(patient__last_name__icontains=search) \
                 | qs.filter(main_objective__icontains=search)

        qs = qs.order_by('-start_date', '-id')

        total_count = qs.count()
        total_pages = (total_count + page_size - 1) // page_size
        offset = (page - 1) * page_size
        results = qs[offset:offset + page_size]

        return PaginatedInterventionPlans(
            results=results,
            total_count=total_count,
            total_pages=total_pages,
            current_page=page
        )

    def resolve_intervention_plan(self, info, id):
        real_id = get_real_id(id)
        try:
            return InterventionPlan.objects.prefetch_related("steps").get(pk=real_id)
        except (InterventionPlan.DoesNotExist, ValueError, TypeError):
            raise GraphQLError(f"Plan con ID {real_id} no encontrado")

    def resolve_therapy_reports(self, info, patient_id=None):
        qs = TherapyReport.objects.select_related("patient", "generated_by").all()
        if patient_id:
            real_patient_id = get_real_id(patient_id)
            qs = qs.filter(patient_id=real_patient_id)
        return qs

    def resolve_patient_growth(self, info):
        last_6_months = {}
        for i in range(5, -1, -1):
            month_dt = timezone.now() - relativedelta(months=i)
            last_6_months[month_dt.strftime('%b')] = 0

        data = (
            Patient.objects.filter(created_at__gte=timezone.now() - relativedelta(months=6))
            .annotate(month_date=TruncMonth('created_at'))
            .values('month_date')
            .annotate(total=Count('id'))
        )

        for item in data:
            month_name = item['month_date'].strftime('%b')
            if month_name in last_6_months:
                last_6_months[month_name] = item['total']

        return [GrowthPointType(month=m, total=t) for m, t in last_6_months.items()]
