import math
import graphene
from decimal import Decimal
from datetime import timedelta
from graphql import GraphQLError
from django.db import transaction
from django.db.models import Max
from django.db.models.functions import Coalesce

from finance.models import CoursePayment, CourseEnrollment, Expense, Payment, Discount, Course
from finance.type import CourseEnrollmentType, ExpenseType, PaymentType, CourseType
from therapeutic_sessions.models import Session
from config.utils import get_db_id

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
        
        real_patient_id = get_db_id(patient_id)
        if not real_patient_id:
            raise GraphQLError("ID de paciente inválido")

        base_total = Decimal(str(price_per_session)) * sessions_count
        final_total = base_total
        
        # Lógica de descuento
        discount_obj = None
        if discount_id:
            try:
                real_discount_id = get_db_id(discount_id)
                discount_obj = Discount.objects.get(pk=real_discount_id)
                if discount_obj.type == Discount.DiscountType.PERCENTAGE:
                    final_total = base_total * (Decimal('1') - (discount_obj.value / Decimal('100')))
                else: # FIXED
                    final_total = base_total - discount_obj.value
            except (Discount.DoesNotExist, ValueError):
                raise GraphQLError("Descuento no encontrado")

        paid = Decimal(str(amount_paid))

        # Determinación de estado basada en el total descontado
        if paid >= final_total:
            status = Payment.PaymentStatus.COMPLETED
        elif paid > 0:
            status = Payment.PaymentStatus.PARTIAL
        else:
            status = Payment.PaymentStatus.PENDING

        with transaction.atomic():
            payment = Payment.objects.create(
                patient_id=real_patient_id,
                sessions_count=sessions_count,
                price_per_session=price_per_session,
                amount_paid=amount_paid,
                payment_method=payment_method,
                discount=discount_obj,
                payment_status=status,
            )

            # ── Lógica de Actualización y Creación de Sesiones ─────────────────
            # 1. Obtener sesiones pendientes del paciente
            pending_sessions = list(Session.objects.filter(
                patient_id=real_patient_id,
                payment_status=Session.PaymentStatus.PENDING
            ).order_by('session_date'))

            sessions_to_mark = min(len(pending_sessions), sessions_count)
            
            # Actualizar las existentes
            for i in range(sessions_to_mark):
                sess = pending_sessions[i]
                sess.payment_status = Session.PaymentStatus.PAID
                sess.save(update_fields=['payment_status', 'updated_at'])

            # 2. Si faltan sesiones por cubrir, crearlas automáticamente
            remaining_to_create = sessions_count - sessions_to_mark
            
            if remaining_to_create > 0:
                # Buscar la última sesión para determinar fecha y terapeuta base
                last_sess = Session.objects.filter(patient_id=real_patient_id).order_by('-session_date').first()
                
                if last_sess:
                    base_date = last_sess.session_date
                    base_therapist_id = last_sess.therapist_id
                    base_type = last_sess.session_type
                    current_session_num = last_sess.session_number
                else:
                    # Si no hay ninguna sesión previa, no podemos automatizar el horario/terapeuta fácilmente
                    # Por ahora lanzamos error para evitar inconsistencias
                    raise GraphQLError("No hay sesiones previas para este paciente. Crea al menos una sesión manual antes de registrar un pago anticipado.")

                new_sessions = []
                for i in range(1, remaining_to_create + 1):
                    current_session_num += 1
                    calculated_cycle = math.ceil(current_session_num / 4)
                    
                    new_sessions.append(
                        Session(
                            patient_id=real_patient_id,
                            therapist_id=base_therapist_id,
                            session_date=base_date + timedelta(weeks=i),
                            session_type=base_type,
                            session_number=current_session_num,
                            cycle_number=calculated_cycle,
                            session_status=Session.SessionStatus.CONFIRMADA,
                            payment_status=Session.PaymentStatus.PAID
                        )
                    )
                
                if new_sessions:
                    Session.objects.bulk_create(new_sessions)

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
        real_course_id = get_db_id(course_id)

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

class UpdatePayment(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        amount_paid = graphene.Float()
        payment_status = graphene.String()

    payment = graphene.Field(PaymentType)

    def mutate(self, info, id, amount_paid=None, payment_status=None):
        try:
            payment = Payment.objects.get(pk=id)
            if amount_paid is not None:
                payment.amount_paid = amount_paid
            if payment_status is not None:
                payment.payment_status = payment_status
            
            # Recalcular estado si se actualiza el monto
            if amount_paid is not None:
                final_total = payment.total_amount
                # Aplicar descuento si existe
                if payment.discount:
                    if payment.discount.type == Discount.DiscountType.PERCENTAGE:
                        final_total = payment.total_amount * (Decimal('1') - (payment.discount.value / Decimal('100')))
                    else:
                        final_total = payment.total_amount - payment.discount.value
                
                if payment.amount_paid >= final_total:
                    payment.payment_status = Payment.PaymentStatus.COMPLETED
                elif payment.amount_paid > 0:
                    payment.payment_status = Payment.PaymentStatus.PARTIAL
                else:
                    payment.payment_status = Payment.PaymentStatus.PENDING

            payment.save()
            return UpdatePayment(payment=payment)
        except Payment.DoesNotExist:
            raise GraphQLError("Pago no encontrado")

class DeletePayment(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    success = graphene.Boolean()

    def mutate(self, info, id):
        try:
            payment = Payment.objects.get(pk=id)
            payment.delete()
            return DeletePayment(success=True)
        except Payment.DoesNotExist:
            return DeletePayment(success=False)

class UpdateExpenseStatus(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        status = graphene.String(required=True)

    expense = graphene.Field(ExpenseType)

    def mutate(self, info, id, status):
        try:
            expense = Expense.objects.get(pk=id)
            expense.status = status
            expense.save()
            return UpdateExpenseStatus(expense=expense)
        except Expense.DoesNotExist:
            raise GraphQLError("Gasto no encontrado")

class DeleteExpense(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    success = graphene.Boolean()

    def mutate(self, info, id):
        try:
            expense = Expense.objects.get(pk=id)
            expense.delete()
            return DeleteExpense(success=True)
        except Expense.DoesNotExist:
            return DeleteExpense(success=False)

class CreateCourse(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        description = graphene.String()
        price = graphene.Float(required=True)
        state = graphene.String()

    course = graphene.Field(CourseType)

    def mutate(self, info, name, price, description=None, state="draft"):
        course = Course.objects.create(
            name=name,
            description=description,
            price=Decimal(str(price)),
            state=state
        )
        return CreateCourse(course=course)

class UpdateCourse(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        name = graphene.String()
        description = graphene.String()
        price = graphene.Float()
        state = graphene.String()

    course = graphene.Field(CourseType)

    def mutate(self, info, id, **kwargs):
        real_id = get_db_id(id)
        try:
            course = Course.objects.get(pk=real_id)
            for key, value in kwargs.items():
                if key == 'price':
                    setattr(course, key, Decimal(str(value)))
                else:
                    setattr(course, key, value)
            course.save()
            return UpdateCourse(course=course)
        except Course.DoesNotExist:
            raise GraphQLError("Curso no encontrado")

class DeleteCourse(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    success = graphene.Boolean()

    def mutate(self, info, id):
        real_id = get_db_id(id)
        try:
            course = Course.objects.get(pk=real_id)
            course.delete()
            return DeleteCourse(success=True)
        except Course.DoesNotExist:
            return DeleteCourse(success=False)

class Mutation(graphene.ObjectType):
    create_payment = CreatePayment.Field()
    update_payment = UpdatePayment.Field()
    delete_payment = DeletePayment.Field()
    create_expense = CreateExpense.Field()
    update_expense_status = UpdateExpenseStatus.Field()
    delete_expense = DeleteExpense.Field()
    enroll_in_course = EnrollInCourse.Field()
    create_course = CreateCourse.Field()
    update_course = UpdateCourse.Field()
    delete_course = DeleteCourse.Field()
