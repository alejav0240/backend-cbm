import random
import string
from datetime import date
import graphene
from django.contrib.auth.hashers import make_password
from django.db import transaction
from clinical.models import Patient, PatientClinicalNote, InterventionPlan, PlanStep, TherapyReport
from clinical.type import PatientType, PatientClinicalNoteType, InterventionPlanType, PlanStepType, TherapyReportType
from users.models import User
from django.db.models import Max
from django.db.models.functions import Coalesce
from config.utils import get_db_id


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

    patient         = graphene.Field(PatientType)
    tutor_username  = graphene.String()
    tutor_password  = graphene.String()
    tutor_created   = graphene.Boolean()

    @transaction.atomic
    def mutate(self, info,
               author_id=None,
               first_name=None, last_name=None,
               ci=None, birth_date=None,
               image_url=None, diagnosis=None,
               residence=None, notes=None,
               tutor_name=None, tutor_celular=None,
               tutor_email=None, tutor_ci=None):

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
        # 1. Asegúrate de que el nombre sea 'id' aquí
        id = graphene.ID(required=True)
        image_url = graphene.String()
        residence = graphene.String()
        diagnosis = graphene.String()
        registration_complete = graphene.Boolean()

    patient = graphene.Field(PatientType)

    # 2. El parámetro DEBE llamarse 'id' para coincidir con Arguments
    def mutate(self, info, id, image_url=None, residence=None, diagnosis=None, registration_complete=None):
        real_id = get_db_id(id)
        try:
            # 3. Usa ese 'id' para buscar al paciente
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

# TODO Revisar si es util
class AddClinicalNote(graphene.Mutation):
    class Arguments:
        patient_id = graphene.ID(required=True)
        author_id = graphene.ID(required=True)
        notes = graphene.List(BasicNote, required=True)

    notes_created = graphene.List(PatientClinicalNoteType)

    def mutate(self, info, patient_id, author_id, notes):
        note_objects = [
            PatientClinicalNote(
                patient_id=patient_id,
                author_id=author_id,
                category=n.category,
                content=n.content
            ) for n in notes
        ]

        created_instances = PatientClinicalNote.objects.bulk_create(note_objects)

        return AddClinicalNote(notes_created=created_instances)

class UpdateClinicalNotes(graphene.Mutation):
    class Arguments:
        patient_id = graphene.ID(required=True)
        author_id = graphene.ID(required=True)
        notes = graphene.List(BasicNote, required=True)

    # Devolvemos la lista de notas actualizadas
    notes_updated = graphene.List(PatientClinicalNoteType)

    def mutate(self, info, patient_id, author_id, notes):
        # Manejar ID de Relay o ID directo para el paciente
        try:
            real_patient_id = int(graphene.relay.Node.from_global_id(patient_id)[1])
        except:
            try:
                real_patient_id = int(patient_id)
            except:
                real_patient_id = patient_id

        updated_instances = []

        for n in notes:
            # Sincronizamos con el modelo usando .upper()
            category_upper = n.category.upper()
            
            note, created = PatientClinicalNote.objects.update_or_create(
                patient_id=real_patient_id,
                category=category_upper,
                defaults={
                    'content': n.content,
                    'author_id': author_id  # Actualiza quién hizo la última edición
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

    def mutate(self, info, patient_id, created_by_id, main_objective,
               start_date=None, end_date=None):
        plan = InterventionPlan.objects.create(
            patient_id=patient_id,
            created_by_id=created_by_id,
            main_objective=main_objective,
            start_date=start_date,
            end_date=end_date,
        )
        return CreateInterventionPlan(plan=plan)

class CreateStepPlan(graphene.Mutation):
    class Arguments:
        plan_id = graphene.ID(required=True)
        moment = graphene.String(required=True)  # Corregido de 'momment'
        duration_minutes = graphene.Int()        # En Graphene es .Int(), no .Integer()
        objective = graphene.String(required=True)
        focus = graphene.String()
        musical_resources = graphene.String()
        musical_emphasis = graphene.String()
        approach = graphene.String()
        mlt_method = graphene.String()
        order_index = graphene.Int()

    # El campo que devuelve la mutación
    step = graphene.Field(PlanStepType) # Asumiendo que ya definiste tu DjangoObjectType

    def mutate(self, info, plan_id, moment, objective, **kwargs):
        # 1. Lógica automática para el índice de orden
        order_index = kwargs.get('order_index')
        if order_index is None:
            last_order = PlanStep.objects.filter(plan_id=plan_id).aggregate(
                max_order=Coalesce(Max('order_index'), 0)
            )
            order_index = last_order['max_order'] + 1

        # 2. Creación del registro
        step = PlanStep.objects.create(
            plan_id=plan_id,
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

    def mutate(self, info, id, progress_percent):
        try:
            plan = InterventionPlan.objects.get(pk=id)
        except InterventionPlan.DoesNotExist:
            raise Exception("Plan de intervención no encontrado")
        
        plan.progress_percent = max(0, min(100, progress_percent))
        plan.save(update_fields=["progress_percent", "updated_at"])
        return UpdatePlanProgress(plan=plan)


class UpdateStepProgress(graphene.Mutation):
    class Arguments:
        step_id = graphene.ID(required=True)
        is_completed = graphene.Boolean()
        actual_duration = graphene.Int()

    # Devolvemos el objeto actualizado
    step = graphene.Field(PlanStepType)
    success = graphene.Boolean()

    def mutate(self, info, step_id, is_completed=None, actual_duration=None):
        try:
            # 1. Buscar el paso del plan
            step = PlanStep.objects.get(pk=step_id)

            # 2. Actualización parcial (solo si los valores vienen en la mutación)
            if is_completed is not None:
                step.is_completed = is_completed

            if actual_duration is not None:
                step.actual_duration = actual_duration

            # 3. Guardar cambios
            step.save()

            return UpdateStepProgress(step=step, success=True)

        except PlanStep.DoesNotExist:
            raise Exception("El paso del plan no existe.")

class DeletePatient(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, id):
        try:
            # En este proyecto usamos IDs directos, pero manejamos la posibilidad de Relay IDs por si acaso
            try:
                real_id = graphene.relay.Node.from_global_id(id)[1]
            except:
                real_id = id

            patient = Patient.objects.get(pk=real_id)
            patient.delete()
            return DeletePatient(success=True, message="Paciente eliminado correctamente")

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

    def mutate(self, info, id, **kwargs):
        try:
            plan = InterventionPlan.objects.get(pk=id)
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

    def mutate(self, info, id):
        try:
            plan = InterventionPlan.objects.get(pk=id)
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

    def mutate(self, info, id, **kwargs):
        try:
            step = PlanStep.objects.get(pk=id)
            for key, value in kwargs.items():
                setattr(step, key, value)
            step.save()
            return UpdateStepPlan(step=step)
        except PlanStep.DoesNotExist:
            raise Exception("Paso no encontrado")

class DeleteStepPlan(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    success = graphene.Boolean()

    def mutate(self, info, id):
        try:
            step = PlanStep.objects.get(pk=id)
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

    def mutate(self, info, patient_id, generated_by_id, report_url):
        report = TherapyReport.objects.create(
            patient_id=patient_id,
            generated_by_id=generated_by_id,
            report_url=report_url
        )
        return CreateTherapyReport(report=report)

class DeleteTherapyReport(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    success = graphene.Boolean()

    def mutate(self, info, id):
        try:
            report = TherapyReport.objects.get(pk=id)
            report.delete()
            return DeleteTherapyReport(success=True)
        except TherapyReport.DoesNotExist:
            return DeleteTherapyReport(success=False)

class Mutation(graphene.ObjectType):
    create_patient = CreatePatient.Field()
    update_patient_status = UpdatePatientStatus.Field()
    add_clinical_note = AddClinicalNote.Field()
    create_intervention_plan = CreateInterventionPlan.Field()
    update_intervention_plan = UpdateInterventionPlan.Field()
    delete_intervention_plan = DeleteInterventionPlan.Field()
    update_plan_progress = UpdatePlanProgress.Field()
    update_patient = UpdatePatient.Field()
    update_clinical_notes = UpdateClinicalNotes.Field()
    create_step_plan = CreateStepPlan.Field()
    update_step_plan = UpdateStepPlan.Field()
    delete_step_plan = DeleteStepPlan.Field()
    update_step_progress = UpdateStepProgress.Field()
    create_therapy_report = CreateTherapyReport.Field()
    delete_therapy_report = DeleteTherapyReport.Field()
    delete_patient = DeletePatient.Field()
