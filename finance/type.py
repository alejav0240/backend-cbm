import graphene
from graphene_django import DjangoObjectType

from finance.models import Discount, Payment, Expense, Course, CourseEnrollment, CoursePayment


class DiscountType(DjangoObjectType):
    class Meta:
        model = Discount
        fields = ("id", "name", "type", "value", "description")


class PaymentType(DjangoObjectType):
    total_amount = graphene.Float()
    debt = graphene.Float()

    class Meta:
        model = Payment
        fields = (
            "id", "patient", "discount",
            "sessions_count", "price_per_session", "amount_paid",
            "payment_method", "payment_date",
            "payment_status", "created_at", "updated_at",
        )

    def resolve_total_amount(self, info):
        return float(self.total_amount)

    def resolve_debt(self, info):
        return float(self.debt)


class ExpenseType(DjangoObjectType):
    class Meta:
        model = Expense
        fields = (
            "id", "description", "category",
            "amount", "expense_date", "status",
            "created_at", "updated_at",
        )


class CourseType(DjangoObjectType):
    students_count = graphene.Int()
    total_income = graphene.Float()

    class Meta:
        model = Course
        fields = ("id", "name", "description", "price", "state", "enrollments")

    def resolve_students_count(self, info):
        return self.enrollments.count()

    def resolve_total_income(self, info):
        from django.db.models import Sum
        result = self.enrollments.aggregate(total=Sum('payment__amount'))
        return result['total'] or 0.0


class CourseEnrollmentType(DjangoObjectType):
    class Meta:
        model = CourseEnrollment
        fields = ("id", "course", "full_name", "carnet", "enrolled_at", "payment")


class CoursePaymentType(DjangoObjectType):
    class Meta:
        model = CoursePayment
        fields = (
            "id", "enrollment",
            "payment_method", "amount",
            "payment_date", "payment_status",
        )


# ── Tipos paginados ────────────────────────────────────────────────────────────

class PaginatedPaymentType(graphene.ObjectType):
    results = graphene.List(PaymentType)
    total_count = graphene.Int()
    total_pages = graphene.Int()
    current_page = graphene.Int()


class PaginatedExpenses(graphene.ObjectType):
    results = graphene.List(ExpenseType)
    total_count = graphene.Int()
    total_pages = graphene.Int()
    current_page = graphene.Int()


class PaginatedCourses(graphene.ObjectType):
    results = graphene.List(CourseType)
    total_count = graphene.Int()
    total_pages = graphene.Int()
    current_page = graphene.Int()


class PaginatedCourseEnrollments(graphene.ObjectType):
    results = graphene.List(CourseEnrollmentType)
    total_count = graphene.Int()
    total_pages = graphene.Int()
    current_page = graphene.Int()
