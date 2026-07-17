import random
import string
from datetime import date
import graphene
from django.contrib.auth.hashers import make_password
from django.db import transaction
from clinical.models import Patient, PatientClinicalNote, InterventionPlan, PlanStep, TherapyReport, SessionPlanStep
from clinical.type import PatientType, PatientClinicalNoteType, InterventionPlanType, PlanStepType, TherapyReportType, SessionPlanStepType
from therapeutic_sessions.models import Session
from users.models import User
from django.db.models import Max
from django.db.models.functions import Coalesce
from config.utils import get_db_id, module_permission_required
import datetime
import math


def _generate_username(last_name: str, ci: str | None) -> str:
    """
    Formato: <apellido_sin_espacios>_<ci_o_random>
    Ejemplo: mamani_12345678
    Si el username ya existe le agrega un sufijo numérico.
    """
    base_last = last_name.lower().strip().replace(" ", "_")
    ci_part = ci.strip() if ci else "".join(random.choices(string.digits, k=6))
    base = f"{base_last}_{ci_part}"

    username = base
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base}_{counter}"
        counter += 1
    return username

def _generate_password(last_name: str, ci: str | None) -> str:
    """
    Formato: <Apellido><ci_o_4random><año_actual>
    Ejemplo: Mamani123456782025
    Se hashea antes de guardar.
    """
    name_part = last_name.strip().capitalize().replace(" ", "")
    ci_part = ci.strip() if ci else "".join(random.choices(string.digits, k=4))
    year = str(date.today().year)
    return f"{name_part}{ci_part}{year}"

def get_next_weekday(start_date, weekday_name):
    days_of_week = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    try:
        target_weekday = days_of_week.index(weekday_name)
    except ValueError:
        return start_date
        
    days_ahead = target_weekday - start_date.weekday()
    if days_ahead <= 0: # Target day already happened this week or is today
        days_ahead += 7
    return start_date + datetime.timedelta(days_ahead)

class CreatePatient(graphene.Mutation):
    class Arguments:
        # autor
        author_id = graphene.ID(required=True)

        # Paciente
        first_name      = graphene.String(required=True)
        last_name       = graphene.String(required=True)
        ci              = graphene.String()
        birth_date      = graphene.Date()
        diagnosis       = graphene.String()
        residence       = graphene.String()
        image_url       = graphene.String()
        notes           = graphene.String()

        # Tutor
        tutor_name      = graphene.String()
        tutor_celular   = graphene.String()
        tutor_email     = graphene.String()
        tutor_ci        = graphene.String()

        # Sesiones Iniciales
        selected_day    = graphene.String()
        selected_time   = graphene.String()

    patient         = graphene.Field(PatientType)
    tutor_username  = graphene.String()
    tutor_password  = graphene.String()
    tutor_created   = graphene.Boolean()

    @transaction.atomic
    @module_permission_required('pacientes', action='add')
    def mutate(self, info,
               author_id=None,
               first_name=None, last_name=None,
               ci=None, birth_date=None,
               image_url=None, diagnosis=None,
               residence=None, notes=None,
               tutor_name=None, tutor_celular=None,
               tutor_email=None, tutor_ci=None,
               selected_day=None, selected_time=None):

        tutor = None
        tutor_username = None
        tutor_password_plain = None
        tutor_created = False

        # ── Tutor ─────────────────────────────────────────────────
        if tutor_name or tutor_email or tutor_ci:

            # 1. Buscar existente: primero por CI, luego por email
            existing = None
            if tutor_ci:
                existing = User.objects.filter(ci=tutor_ci).first()
            if not existing and tutor_email:
                existing = User.objects.filter(email=tutor_email).first()

            if existing:
                tutor = existing
                tutor_created = False

            else:
                if not tutor_name:
                    raise Exception(
                        "tutor_name es requerido para registrar un tutor nuevo."
                    )

                name_parts  = tutor_name.strip().split()
                tutor_first = name_parts[0]
                tutor_last  = " ".join(name_parts[1:]) if len(name_parts) > 1 else last_name

                tutor_username      = _generate_username(last_name, tutor_ci)
                tutor_password_plain = _generate_password(last_name, tutor_ci)

                tutor = User.objects.create(
                    username   = tutor_username,
                    password   = make_password(tutor_password_plain),
                    email      = tutor_email or f"{tutor_username}@sin-email.cbm",
                    first_name = tutor_first,
                    last_name  = tutor_last,
                    ci         = tutor_ci,
                    celular      = tutor_celular,
                    is_active  = True,
                )
                tutor_created = True

        # ── Paciente ──────────────────────────────────────────────
        patient = Patient.objects.create(
            first_name  = first_name,
            last_name   = last_name,
            ci          = ci,                          # campo directo en el modelo real
            birth_date  = birth_date,
            diagnosis   = diagnosis or "sin diagnostico",  # default del modelo
            residence   = residence,
            image_url   = image_url,
            notes       = notes,
            tutor       = tutor,
            registration_complete = False,
        )

        # Clinical notes
        categories_to_create = [
            PatientClinicalNote.Category.GENERAL_OBJECTIVE,
            PatientClinicalNote.Category.PHYSICAL_AREA,
            PatientClinicalNote.Category.EMOTIONAL_AREA,
            PatientClinicalNote.Category.COGNITIVE_AREA,
            PatientClinicalNote.Category.SOCIAL_AREA,
            PatientClinicalNote.Category.METHODS,
            PatientClinicalNote.Category.ADDITIONAL_NOTES,
        ]

        default_notes = [
            PatientClinicalNote(
                patient=patient,
                author_id=author_id,
                category=cat_value,
                content="Sin registro"  # Texto por defecto
            ) for cat_value in categories_to_create
        ]

        PatientClinicalNote.objects.bulk_create(default_notes)

        # ── Sesiones Iniciales (Ciclo de 4) ───────────────────────
        if selected_day and selected_time:
            try:
                # Calcular la primera fecha
                today = datetime.date.today()
                first_session_date = get_next_weekday(today, selected_day)
                
                # Parsear la hora
                hour, minute = map(int, selected_time.split(':'))
                
                # Combinar fecha y hora
                start_datetime = datetime.datetime.combine(first_session_date, datetime.time(hour, minute))
                
                sessions_to_create = []
                for i in range(4):
                    session_number = i + 1
                    calculated_cycle = math.ceil(session_number / 4)
                    
                    # Programar una sesión cada semana (7 días)
                    session_date = start_datetime + datetime.timedelta(weeks=i)
                    
                    sessions_to_create.append(
                        Session(
                            patient=patient,
                            therapist_id=author_id,
                            session_date=session_date,
                            session_type="individual",
                            session_number=session_number,
                            cycle_number=calculated_cycle,
                            session_status="agendada", # Antes "confirma"
                            payment_status="pending"
                        )
                    )
                Session.objects.bulk_create(sessions_to_create)
            except Exception as e:
                # No queremos que falle el registro del paciente si fallan las sesiones
                print(f"Error creando sesiones iniciales: {e}")

        return CreatePatient(
            patient        = patient,
            tutor_username = tutor_username,
            tutor_password = tutor_password_plain,
            tutor_created  = tutor_created,
        )


class UpdatePatientStatus(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        status = graphene.String(required=True)

    patient = graphene.Field(PatientType)

    @module_permission_required('pacientes', action='change')
    def mutate(self, info, id, status):
        real_id = get_db_id(id)

        try:
            patient = Patient.objects.get(pk=real_id)
        except Patient.DoesNotExist:
            raise Exception("Paciente no encontrado")

        patient.status = status
        patient.save(update_fields=["status", "updated_at"])
        return UpdatePatientStatus(patient=patient)

class UpdatePatient(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        image_url = graphene.String()
        residence = graphene.String()
        diagnosis = graphene.String()
        registration_complete = graphene.Boolean()

    patient = graphene.Field(PatientType)

    @module_permission_required('pacientes', action='change')
    def mutate(self, info, id, image_url=None, residence=None, diagnosis=None, registration_complete=None):
        real_id = get_db_id(id)
        try:
            patient = Patient.objects.get(pk=real_id)

            if image_url is not None:
                patient.image_url = image_url
            if residence is not None:
                patient.residence = residence
            if diagnosis is not None:
                patient.diagnosis = diagnosis
            if registration_complete is not None:
                patient.registration_complete = registration_complete

            patient.save()
            return UpdatePatient(patient=patient)

        except Patient.DoesNotExist:
            raise Exception("Paciente no encontrado")

class BasicNote(graphene.InputObjectType):
    category = graphene.String()
    content = graphene.String()

class UpdateClinicalNotes(graphene.Mutation):
    class Arguments:
        patient_id = graphene.ID(required=True)
        author_id = graphene.ID(required=True)
        notes = graphene.List(BasicNote, required=True)

    notes_updated = graphene.List(PatientClinicalNoteType)

    @module_permission_required('pacientes', action='change')
    def mutate(self, info, patient_id, author_id, notes):
        real_patient_id = get_db_id(patient_id)
        real_author_id = get_db_id(author_id)
        updated_instances = []

        for n in notes:
            category_upper = n.category.upper()
            
            note, created = PatientClinicalNote.objects.update_or_create(
                patient_id=real_patient_id,
                category=category_upper,
                defaults={
                    'content': n.content,
                    'author_id': real_author_id
                }
            )
            updated_instances.append(note)

        return UpdateClinicalNotes(notes_updated=updated_instances)

class CreateInterventionPlan(graphene.Mutation):
    class Arguments:
        patient_id = graphene.ID(required=True)
        created_by_id = graphene.ID(required=True)
        main_objective = graphene.String(required=True)
        start_date = graphene.Date()
        end_date = graphene.Date()

    plan = graphene.Field(InterventionPlanType)

    @module_permission_required('planes', action='add')
    def mutate(self, info, patient_id, created_by_id, main_objective,
               start_date=None, end_date=None):
        plan = InterventionPlan.objects.create(
            patient_id=get_db_id(patient_id),
            created_by_id=get_db_id(created_by_id),
            main_objective=main_objective,
            start_date=start_date,
            end_date=end_date,
        )
        return CreateInterventionPlan(plan=plan)

class CreateStepPlan(graphene.Mutation):
    class Arguments:
        plan_id = graphene.ID(required=True)
        moment = graphene.String(required=True)
        duration_minutes = graphene.Int()
        objective = graphene.String(required=True)
        focus = graphene.String()
        musical_resources = graphene.String()
        musical_emphasis = graphene.String()
        approach = graphene.String()
        mlt_method = graphene.String()
        order_index = graphene.Int()

    step = graphene.Field(PlanStepType)

    @module_permission_required('planes', action='change')
    def mutate(self, info, plan_id, moment, objective, **kwargs):
        real_plan_id = get_db_id(plan_id)
        order_index = kwargs.get('order_index')
        if order_index is None:
            last_order = PlanStep.objects.filter(plan_id=real_plan_id).aggregate(
                max_order=Coalesce(Max('order_index'), 0)
            )
            order_index = last_order['max_order'] + 1

        step = PlanStep.objects.create(
            plan_id=real_plan_id,
            moment=moment,
            objective=objective,
            duration_minutes=kwargs.get('duration_minutes'),
            focus=kwargs.get('focus'),
            musical_resources=kwargs.get('musical_resources'),
            musical_emphasis=kwargs.get('musical_emphasis'),
            approach=kwargs.get('approach'),
            mlt_method=kwargs.get('mlt_method'),
            order_index=order_index
        )

        return CreateStepPlan(step=step)

class UpdatePlanProgress(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        progress_percent = graphene.Int(required=True)

    plan = graphene.Field(InterventionPlanType)

    @module_permission_required('planes', action='change')
    def mutate(self, info, id, progress_percent):
        real_id = get_db_id(id)
        try:
            plan = InterventionPlan.objects.get(pk=real_id)
        except InterventionPlan.DoesNotExist:
            raise Exception("Plan de intervención no encontrado")
        
        plan.progress_percent = max(0, min(100, progress_percent))
        plan.save(update_fields=["progress_percent", "updated_at"])
        return UpdatePlanProgress(plan=plan)

class DeletePatient(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    @module_permission_required('pacientes', action='delete')
    def mutate(self, info, id):
        real_id = get_db_id(id)
        try:
            patient = Patient.objects.get(pk=real_id)
            patient.status = Patient.Status.INACTIVE
            patient.save(update_fields=['status'])
            return DeletePatient(success=True, message="Paciente desactivado correctamente")
        except Patient.DoesNotExist:
            return DeletePatient(success=False, message="El paciente no existe")
        except Exception as e:
            return DeletePatient(success=False, message=str(e))

class UpdateInterventionPlan(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        main_objective = graphene.String()
        start_date = graphene.Date()
        end_date = graphene.Date()

    plan = graphene.Field(InterventionPlanType)

    @module_permission_required('planes', action='change')
    def mutate(self, info, id, **kwargs):
        real_id = get_db_id(id)
        try:
            plan = InterventionPlan.objects.get(pk=real_id)
            for key, value in kwargs.items():
                setattr(plan, key, value)
            plan.save()
            return UpdateInterventionPlan(plan=plan)
        except InterventionPlan.DoesNotExist:
            raise Exception("Plan no encontrado")

class DeleteInterventionPlan(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    success = graphene.Boolean()

    @module_permission_required('planes', action='delete')
    def mutate(self, info, id):
        real_id = get_db_id(id)
        try:
            plan = InterventionPlan.objects.get(pk=real_id)
            plan.delete()
            return DeleteInterventionPlan(success=True)
        except InterventionPlan.DoesNotExist:
            return DeleteInterventionPlan(success=False)

class UpdateStepPlan(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        moment = graphene.String()
        duration_minutes = graphene.Int()
        objective = graphene.String()
        focus = graphene.String()
        musical_resources = graphene.String()
        musical_emphasis = graphene.String()
        approach = graphene.String()
        mlt_method = graphene.String()

    step = graphene.Field(PlanStepType)

    @module_permission_required('planes', action='change')
    def mutate(self, info, id, **kwargs):
        real_id = get_db_id(id)
        try:
            step = PlanStep.objects.get(pk=real_id)
            for key, value in kwargs.items():
                setattr(step, key, value)
            step.save()
            return UpdateStepPlan(step=step)
        except PlanStep.DoesNotExist:
            raise Exception("Paso no encontrado")


# ─────────────────────────────────────────
# SessionPlanStep — control de ejecución por sesión
# ─────────────────────────────────────────

class AddStepToSession(graphene.Mutation):
    """Asocia un PlanStep a una sesión, creando el registro de control si no existe."""
    class Arguments:
        session_id = graphene.ID(required=True)
        plan_step_id = graphene.ID(required=True)
        is_completed = graphene.Boolean()
        actual_duration = graphene.Int()
        notes = graphene.String()

    session_plan_step = graphene.Field(SessionPlanStepType)

    @module_permission_required('planes', action='change')
    def mutate(self, info, session_id, plan_step_id,
               is_completed=False, actual_duration=None, notes=None):
        real_session_id = get_db_id(session_id)
        real_step_id = get_db_id(plan_step_id)

        sps, _ = SessionPlanStep.objects.get_or_create(
            session_id=real_session_id,
            plan_step_id=real_step_id,
            defaults={
                "is_completed": is_completed,
                "actual_duration": actual_duration,
                "notes": notes,
            },
        )
        return AddStepToSession(session_plan_step=sps)


class UpdateSessionPlanStep(graphene.Mutation):
    """Actualiza el estado de ejecución de un paso dentro de una sesión."""
    class Arguments:
        session_id = graphene.ID(required=True)
        plan_step_id = graphene.ID(required=True)
        is_completed = graphene.Boolean()
        actual_duration = graphene.Int()
        notes = graphene.String()

    session_plan_step = graphene.Field(SessionPlanStepType)

    @module_permission_required('planes', action='change')
    def mutate(self, info, session_id, plan_step_id,
               is_completed=None, actual_duration=None, notes=None):
        real_session_id = get_db_id(session_id)
        real_step_id = get_db_id(plan_step_id)

        try:
            sps = SessionPlanStep.objects.get(
                session_id=real_session_id,
                plan_step_id=real_step_id,
            )
        except SessionPlanStep.DoesNotExist:
            raise Exception("No existe ese paso asociado a la sesión. Usa addStepToSession primero.")

        if is_completed is not None:
            sps.is_completed = is_completed
        if actual_duration is not None:
            sps.actual_duration = actual_duration
        if notes is not None:
            sps.notes = notes
        sps.save()
        return UpdateSessionPlanStep(session_plan_step=sps)


class RemoveStepFromSession(graphene.Mutation):
    """Desasocia un PlanStep de una sesión."""
    class Arguments:
        session_id = graphene.ID(required=True)
        plan_step_id = graphene.ID(required=True)

    success = graphene.Boolean()

    @module_permission_required('planes', action='change')
    def mutate(self, info, session_id, plan_step_id):
        real_session_id = get_db_id(session_id)
        real_step_id = get_db_id(plan_step_id)
        deleted, _ = SessionPlanStep.objects.filter(
            session_id=real_session_id,
            plan_step_id=real_step_id,
        ).delete()
        return RemoveStepFromSession(success=deleted > 0)

class DeleteStepPlan(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    success = graphene.Boolean()

    @module_permission_required('planes', action='delete')
    def mutate(self, info, id):
        real_id = get_db_id(id)
        try:
            step = PlanStep.objects.get(pk=real_id)
            step.delete()
            return DeleteStepPlan(success=True)
        except PlanStep.DoesNotExist:
            return DeleteStepPlan(success=False)

class CreateTherapyReport(graphene.Mutation):
    class Arguments:
        patient_id = graphene.ID(required=True)
        generated_by_id = graphene.ID(required=True)
        report_url = graphene.String(required=True)

    report = graphene.Field(TherapyReportType)

    @module_permission_required('informes', action='add')
    def mutate(self, info, patient_id, generated_by_id, report_url):
        report = TherapyReport.objects.create(
            patient_id=get_db_id(patient_id),
            generated_by_id=get_db_id(generated_by_id),
            report_url=report_url
        )
        return CreateTherapyReport(report=report)

class DeleteTherapyReport(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    success = graphene.Boolean()

    @module_permission_required('informes', action='delete')
    def mutate(self, info, id):
        real_id = get_db_id(id)
        try:
            report = TherapyReport.objects.get(pk=real_id)
            report.delete()
            return DeleteTherapyReport(success=True)
        except TherapyReport.DoesNotExist:
            return DeleteTherapyReport(success=False)

class Mutation(graphene.ObjectType):
    create_patient = CreatePatient.Field()
    update_patient_status = UpdatePatientStatus.Field()
    create_intervention_plan = CreateInterventionPlan.Field()
    update_intervention_plan = UpdateInterventionPlan.Field()
    delete_intervention_plan = DeleteInterventionPlan.Field()
    update_plan_progress = UpdatePlanProgress.Field()
    update_patient = UpdatePatient.Field()
    update_clinical_notes = UpdateClinicalNotes.Field()
    create_step_plan = CreateStepPlan.Field()
    update_step_plan = UpdateStepPlan.Field()
    delete_step_plan = DeleteStepPlan.Field()
    create_therapy_report = CreateTherapyReport.Field()
    delete_therapy_report = DeleteTherapyReport.Field()
    delete_patient = DeletePatient.Field()
    # SessionPlanStep
    add_step_to_session = AddStepToSession.Field()
    update_session_plan_step = UpdateSessionPlanStep.Field()
    remove_step_from_session = RemoveStepFromSession.Field()
