from django.db.models import Q
import graphene
from graphql import GraphQLError
from finance.models import Discount, Payment, Expense, Course, CourseEnrollment
from finance.type import DiscountType, PaymentType, ExpenseType, CourseType, CourseEnrollmentType, PaginatedPaymentType, PaginatedExpenses, PaginatedCourses, PaginatedCourseEnrollments
from config.utils import module_permission_required, get_db_id

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

    expenses = graphene.Field(
        PaginatedExpenses,
        status=graphene.String(),
        category=graphene.String(),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
    )

    courses = graphene.Field(
        PaginatedCourses,
        state=graphene.String(),
        search=graphene.String(),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
    )
    course = graphene.Field(CourseType, id=graphene.ID(required=True))

    course_enrollments = graphene.Field(
        PaginatedCourseEnrollments,
        course_id=graphene.ID(),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
    )

    @module_permission_required('pagos', action='view')
    def resolve_discounts(self, info):
        return Discount.objects.all()

    @module_permission_required('pagos', action='view')
    def resolve_payments(self, info, patient_id=None, payment_status=None, search=None, page=1, page_size=10):
        qs = Payment.objects.select_related("patient", "discount").all()
        if patient_id:
            real_patient_id = get_db_id(patient_id)
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
            results=objects,
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )

    @module_permission_required('pagos', action='view')
    def resolve_payment(self, info, id):
        real_id = get_db_id(id)
        try:
            return Payment.objects.select_related("patient", "discount").get(pk=real_id)
        except Payment.DoesNotExist:
            raise GraphQLError("Pago no encontrado")

    @module_permission_required('gastos', action='view')
    def resolve_expenses(self, info, status=None, category=None, page=1, page_size=10):
        qs = Expense.objects.all()
        if status:
            qs = qs.filter(status=status)
        if category:
            qs = qs.filter(category__icontains=category)
        total_count = qs.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        offset = (page - 1) * page_size
        return PaginatedExpenses(
            results=qs[offset:offset + page_size],
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )

    @module_permission_required('cursos', action='view')
    def resolve_courses(self, info, state=None, search=None, page=1, page_size=10):
        qs = Course.objects.prefetch_related("enrollments").all()
        if state:
            qs = qs.filter(state=state)
        if search:
            qs = qs.filter(name__icontains=search)
        total_count = qs.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        offset = (page - 1) * page_size
        return PaginatedCourses(
            results=qs[offset:offset + page_size],
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )

    @module_permission_required('cursos', action='view')
    def resolve_course(self, info, id):
        real_id = get_db_id(id)
        try:
            return Course.objects.prefetch_related("enrollments__payment").get(pk=real_id)
        except Course.DoesNotExist:
            raise GraphQLError("Curso no encontrado")

    @module_permission_required('cursos', action='view')
    def resolve_course_enrollments(self, info, course_id=None, page=1, page_size=10):
        qs = CourseEnrollment.objects.select_related("course").all()
        if course_id:
            qs = qs.filter(course_id=get_db_id(course_id))
        total_count = qs.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        offset = (page - 1) * page_size
        return PaginatedCourseEnrollments(
            results=qs[offset:offset + page_size],
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )
