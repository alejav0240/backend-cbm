import graphene
from decimal import Decimal
from graphql import GraphQLError
from finance.models import CoursePayment, CourseEnrollment, Expense, Payment, Discount, Course
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
        
        try:
            real_patient_id = int(graphene.relay.Node.from_global_id(patient_id)[1])
        except:
            real_patient_id = patient_id

        base_total = Decimal(str(price_per_session)) * sessions_count
        final_total = base_total
        
        # Lógica de descuento
        discount_obj = None
        if discount_id:
            try:
                try:
                    real_discount_id = int(graphene.relay.Node.from_global_id(discount_id)[1])
                except:
                    real_discount_id = discount_id
                    
                discount_obj = Discount.objects.get(pk=real_discount_id)
                if discount_obj.type == Discount.DiscountType.PERCENTAGE:
                    final_total = base_total * (Decimal('1') - (discount_obj.value / Decimal('100')))
                else: # FIXED
                    final_total = base_total - discount_obj.value
            except Discount.DoesNotExist:
                raise GraphQLError("Descuento no encontrado")

        paid = Decimal(str(amount_paid))

        # Determinación de estado basada en el total descontado
        if paid >= final_total:
            status = Payment.PaymentStatus.COMPLETED
        elif paid > 0:
            status = Payment.PaymentStatus.PARTIAL
        else:
            status = Payment.PaymentStatus.PENDING

        payment = Payment.objects.create(
            patient_id=real_patient_id,
            sessions_count=sessions_count,
            price_per_session=price_per_session,
            amount_paid=amount_paid,
            payment_method=payment_method,
            discount=discount_obj,
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
        full_name = graphene.String(required=True)
        carnet = graphene.String()
        payment_method = graphene.String(required=True)
        amount = graphene.Float(required=True)

    enrollment = graphene.Field(CourseEnrollmentType)

    def mutate(self, info, course_id, full_name, payment_method,
               amount, carnet=None):
        try:
            real_course_id = int(graphene.relay.Node.from_global_id(course_id)[1])
        except:
            real_course_id = course_id

        try:
            # Verificamos que el curso exista antes de enrolar
            Course.objects.get(pk=real_course_id)
        except Course.DoesNotExist:
            raise GraphQLError("Curso no encontrado")

        # Eliminada referencia a user_id que no está en el modelo
        enrollment, created = CourseEnrollment.objects.get_or_create(
            course_id=real_course_id,
            full_name=full_name,
            defaults={"carnet": carnet},
        )
        if created:
            CoursePayment.objects.create(
                enrollment=enrollment,
                payment_method=payment_method,
                amount=amount,
                payment_status="completed" # Asumimos completado si se crea en el momento
            )
        return EnrollInCourse(enrollment=enrollment)

class Mutation(graphene.ObjectType):
    create_payment = CreatePayment.Field()
    create_expense = CreateExpense.Field()
    enroll_in_course = EnrollInCourse.Field()
