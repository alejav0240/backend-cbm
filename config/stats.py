import graphene
from django.utils import timezone
from django.db.models import Count, Sum
from clinical.models import Patient
from therapeutic_sessions.models import Session
from finance.models import Payment, Expense
from django.contrib.auth.models import Group
from config.utils import login_required

class DashboardStatsType(graphene.ObjectType):
    active_patients_count = graphene.Int()
    active_cycles_count = graphene.Int()
    today_sessions_count = graphene.Int()
    monthly_income = graphene.Float()
    monthly_expenses = graphene.Float()

class Query(graphene.ObjectType):
    dashboard_stats = graphene.Field(DashboardStatsType)

    @login_required
    def resolve_dashboard_stats(self, info):
        user = info.context.user
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Permisos básicos para el dashboard (solo staff o con permisos de ver pacientes/sesiones)
        can_view_stats = user.is_staff or user.is_superuser or user.has_perm('clinical.view_patient')

        if not can_view_stats:
            return DashboardStatsType(
                active_patients_count=0,
                active_cycles_count=0,
                today_sessions_count=0,
                monthly_income=0,
                monthly_expenses=0
            )

        active_patients = Patient.objects.filter(status='Activo').count()
        
        from therapeutic_sessions.queries import _build_cycles
        all_cycles = _build_cycles(Session.objects.filter(cycle_number__isnull=False))
        active_cycles = sum(1 for c in all_cycles if c.status == "Activo")

        today_sessions = Session.objects.filter(
            session_date__date=now.date()
        ).count()

        # Las finanzas solo las ve el staff o quien tiene permiso de pagos
        can_view_finance = user.is_staff or user.is_superuser or user.has_perm('finance.view_payment')
        
        monthly_income = 0
        monthly_expenses = 0
        
        if can_view_finance:
            monthly_income = Payment.objects.filter(
                payment_date__gte=start_of_month,
                payment_status='completed'
            ).aggregate(total=Sum('amount_paid'))['total'] or 0

            monthly_expenses = Expense.objects.filter(
                expense_date__gte=start_of_month,
                status='paid'
            ).aggregate(total=Sum('amount'))['total'] or 0

        return DashboardStatsType(
            active_patients_count=active_patients,
            active_cycles_count=active_cycles,
            today_sessions_count=today_sessions,
            monthly_income=float(monthly_income),
            monthly_expenses=float(monthly_expenses)
        )
