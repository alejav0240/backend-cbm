from django.utils import timezone
import graphene
from graphql import GraphQLError
from dateutil.relativedelta import relativedelta
from django.db.models import Count
from django.db.models.functions import TruncMonth
import base64

from .models import Patient, PatientClinicalNote, InterventionPlan, TherapyReport, SessionPlanStep
from .type import PatientType, PatientClinicalNoteType, InterventionPlanType, TherapyReportType, GrowthPointType, SessionPlanStepType
from config.utils import login_required, get_db_id, module_permission_required

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

    session_plan_steps = graphene.List(
        SessionPlanStepType,
        session_id=graphene.ID(),
        plan_step_id=graphene.ID(),
        plan_id=graphene.ID(),
        is_completed=graphene.Boolean(),
        description="Registros de ejecución de pasos del plan por sesión.",
    )

    patient_growth = graphene.List(GrowthPointType)

    @module_permission_required('pacientes', action='view')
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

    @module_permission_required('pacientes', action='view')
    def resolve_patient(self, info, id):
        real_id = get_db_id(id)
        try:
            return Patient.objects.select_related("tutor").get(pk=real_id)
        except (Patient.DoesNotExist, ValueError, TypeError):
            raise GraphQLError(f"Paciente con ID {real_id} no encontrado")

    @login_required
    def resolve_clinical_notes(self, info, patient_id, category=None):
        real_patient_id = get_db_id(patient_id)
        qs = PatientClinicalNote.objects.filter(patient_id=real_patient_id).select_related("author")
        if category:
            qs = qs.filter(category=category)
        return qs

    @module_permission_required('planes', action='view')
    def resolve_intervention_plans(self, info, patient_id=None, search=None, page=1, page_size=10):
        qs = InterventionPlan.objects.select_related("patient").prefetch_related("steps").all()
        if patient_id:
            real_patient_id = get_db_id(patient_id)
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

    @login_required
    def resolve_intervention_plan(self, info, id):
        real_id = get_db_id(id)
        try:
            return InterventionPlan.objects.prefetch_related(
                "steps__session_executions"
            ).get(pk=real_id)
        except (InterventionPlan.DoesNotExist, ValueError, TypeError):
            raise GraphQLError(f"Plan con ID {real_id} no encontrado")

    @module_permission_required('informes', action='view')
    def resolve_therapy_reports(self, info, patient_id=None):
        qs = TherapyReport.objects.select_related("patient", "generated_by").all()
        if patient_id:
            real_patient_id = get_db_id(patient_id)
            qs = qs.filter(patient_id=real_patient_id)
        return qs

    @module_permission_required('planes', action='view')
    def resolve_session_plan_steps(self, info, session_id=None, plan_step_id=None,
                                   plan_id=None, is_completed=None):
        qs = SessionPlanStep.objects.select_related(
            "session__patient",
            "plan_step__plan",
        ).all()

        if session_id:
            qs = qs.filter(session_id=get_db_id(session_id))
        if plan_step_id:
            qs = qs.filter(plan_step_id=get_db_id(plan_step_id))
        if plan_id:
            qs = qs.filter(plan_step__plan_id=get_db_id(plan_id))
        if is_completed is not None:
            qs = qs.filter(is_completed=is_completed)

        return qs

    @login_required
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
