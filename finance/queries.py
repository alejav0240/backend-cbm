from django.db.models import Q
import graphene
from graphql import GraphQLError
from finance.models import Discount, Payment, Expense, Course, CourseEnrollment
from finance.type import DiscountType, PaymentType, ExpenseType, CourseType, CourseEnrollmentType, PaginatedPaymentType

class Query(graphene.ObjectType):
    discounts = graphene.List(DiscountType)
    payments = graphene.Field(
        PaginatedPaymentType,
        patient_id=graphene.ID(),
        payment_status=graphene.String(),
        search=graphene.String(),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
    )
    payment = graphene.Field(PaymentType, id=graphene.ID(required=True))

    expenses = graphene.List(
        ExpenseType,
        status=graphene.String(),
        category=graphene.String(),
    )

    courses = graphene.List(CourseType, state=graphene.String())
    course = graphene.Field(CourseType, id=graphene.ID(required=True))

    course_enrollments = graphene.List(
        CourseEnrollmentType,
        course_id=graphene.ID(),
    )

    def resolve_discounts(self, info):
        return Discount.objects.all()

    def resolve_payments(self, info, patient_id=None, payment_status=None, search=None, page=1, page_size=10):
        qs = Payment.objects.select_related("patient", "discount").all()
        if patient_id:
            try:
                from graphql_relay import from_global_id
                real_patient_id = from_global_id(patient_id)[1]
            except:
                real_patient_id = patient_id
            qs = qs.filter(patient_id=real_patient_id)
        if payment_status:
            qs = qs.filter(payment_status=payment_status)
        if search:
            qs = qs.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search)
            )

        total_count = qs.count()
        total_pages = (total_count + page_size - 1) // page_size
        offset = (page - 1) * page_size
        objects = qs[offset:offset + page_size]

        return PaginatedPaymentType(
            objects=objects,
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )

    def resolve_payment(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        try:
            return Payment.objects.select_related("patient", "discount").get(pk=real_id)
        except Payment.DoesNotExist:
            raise GraphQLError("Pago no encontrado")

    def resolve_expenses(self, info, status=None, category=None):
        qs = Expense.objects.all()
        if status:
            qs = qs.filter(status=status)
        if category:
            qs = qs.filter(category__icontains=category)
        return qs

    def resolve_courses(self, info, state=None):
        qs = Course.objects.prefetch_related("enrollments").all()
        if state:
            qs = qs.filter(state=state)
        return qs

    def resolve_course(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        try:
            return Course.objects.prefetch_related("enrollments__payment").get(pk=real_id)
        except Course.DoesNotExist:
            raise GraphQLError("Curso no encontrado")

    def resolve_course_enrollments(self, info, course_id=None):
        qs = CourseEnrollment.objects.select_related("course").all()
        if course_id:
            try:
                real_course_id = int(graphene.relay.Node.from_global_id(course_id)[1])
            except:
                real_course_id = course_id
            qs = qs.filter(course_id=real_course_id)
        return qs
