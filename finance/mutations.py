import graphene

from finance.models import CoursePayment, CourseEnrollment, Expense, Payment
from finance.type import CourseEnrollmentType, ExpenseType, PaymentType


class CreatePayment(graphene.Mutation):
    class Arguments:
        patient_id = graphene.ID(required=True)
        sessions_count = graphene.Int(required=True)
        price_per_session = graphene.Float(required=True)
        amount_paid = graphene.Float(required=True)
        payment_method = graphene.String(required=True)
        discount_id = graphene.ID()

    payment = graphene.Field(PaymentType)

    def mutate(self, info, patient_id, sessions_count, price_per_session,
               amount_paid, payment_method, discount_id=None):
        from decimal import Decimal
        total = Decimal(str(price_per_session)) * sessions_count
        paid = Decimal(str(amount_paid))

        if paid >= total:
            status = "completed"
        elif paid > 0:
            status = "partial"
        else:
            status = "pending"

        payment = Payment.objects.create(
            patient_id=patient_id,
            sessions_count=sessions_count,
            price_per_session=price_per_session,
            amount_paid=amount_paid,
            payment_method=payment_method,
            discount_id=discount_id,
            payment_status=status,
        )
        return CreatePayment(payment=payment)


class CreateExpense(graphene.Mutation):
    class Arguments:
        description = graphene.String(required=True)
        category = graphene.String(required=True)
        amount = graphene.Float(required=True)
        expense_date = graphene.DateTime(required=True)

    expense = graphene.Field(ExpenseType)

    def mutate(self, info, description, category, amount, expense_date):
        expense = Expense.objects.create(
            description=description,
            category=category,
            amount=amount,
            expense_date=expense_date,
        )
        return CreateExpense(expense=expense)


class EnrollInCourse(graphene.Mutation):
    class Arguments:
        course_id = graphene.ID(required=True)
        user_id = graphene.ID(required=True)
        full_name = graphene.String(required=True)
        carnet = graphene.String()
        payment_method = graphene.String(required=True)
        amount = graphene.Float(required=True)

    enrollment = graphene.Field(CourseEnrollmentType)

    def mutate(self, info, course_id, user_id, full_name, payment_method,
               amount, carnet=None):
        enrollment, created = CourseEnrollment.objects.get_or_create(
            course_id=course_id,
            user_id=user_id,
            defaults={"full_name": full_name, "carnet": carnet},
        )
        if created:
            CoursePayment.objects.create(
                enrollment=enrollment,
                payment_method=payment_method,
                amount=amount,
            )
        return EnrollInCourse(enrollment=enrollment)


class Mutation(graphene.ObjectType):
    create_payment = CreatePayment.Field()
    create_expense = CreateExpense.Field()
    enroll_in_course = EnrollInCourse.Field()