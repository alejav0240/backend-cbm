import graphene
from django.utils import timezone
from django.db.models import Count, Sum
from clinical.models import Patient
from therapeutic_sessions.models import Session
from finance.models import Payment, Expense
from django.contrib.auth.models import Group

class DashboardStatsType(graphene.ObjectType):
    active_patients_count = graphene.Int()
    active_cycles_count = graphene.Int()
    today_sessions_count = graphene.Int()
    monthly_income = graphene.Float()
    monthly_expenses = graphene.Float()

class Query(graphene.ObjectType):
    dashboard_stats = graphene.Field(DashboardStatsType)

    def resolve_dashboard_stats(self, info):
        user = info.context.user
        if not user.is_authenticated:
            return None

        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        active_patients = Patient.objects.filter(status='Activo').count()
        
        # Conteo de ciclos activos (donde al menos una sesión no está completa)
        # Nota: Esto es una simplificación basada en la lógica de _build_cycles
        from therapeutic_sessions.queries import _build_cycles
        all_cycles = _build_cycles(Session.objects.filter(cycle_number__isnull=False))
        active_cycles = sum(1 for c in all_cycles if c.status == "Activo")

        today_sessions = Session.objects.filter(
            session_date__date=now.date()
        ).count()

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
