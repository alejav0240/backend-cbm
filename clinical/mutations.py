import graphene

from clinical.models import Patient, PatientClinicalNote, InterventionPlan
from clinical.type import PatientType, PatientClinicalNoteType, InterventionPlanType


class CreatePatient(graphene.Mutation):
    class Arguments:
        first_name = graphene.String(required=True)
        last_name = graphene.String(required=True)
        ci = graphene.String()
        birth_date = graphene.Date()
        image_url = graphene.String()
        notes = graphene.String()
        tutor_id = graphene.ID()

    patient = graphene.Field(PatientType)

    def mutate(self, info, first_name, last_name, ci=None,
               birth_date=None, image_url=None, notes=None, tutor_id=None):
        patient = Patient.objects.create(
            first_name=first_name,
            last_name=last_name,
            ci=ci,
            birth_date=birth_date,
            image_url=image_url,
            notes=notes,
            tutor_id=tutor_id,
        )
        return CreatePatient(patient=patient)


class UpdatePatientStatus(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        status = graphene.String(required=True)

    patient = graphene.Field(PatientType)

    def mutate(self, info, id, status):
        patient = Patient.objects.get(pk=id)
        patient.status = status
        patient.save(update_fields=["status", "updated_at"])
        return UpdatePatientStatus(patient=patient)


class AddClinicalNote(graphene.Mutation):
    class Arguments:
        patient_id = graphene.ID(required=True)
        author_id = graphene.ID(required=True)
        category = graphene.String(required=True)
        content = graphene.String(required=True)

    note = graphene.Field(PatientClinicalNoteType)

    def mutate(self, info, patient_id, author_id, category, content):
        note = PatientClinicalNote.objects.create(
            patient_id=patient_id,
            author_id=author_id,
            category=category,
            content=content,
        )
        return AddClinicalNote(note=note)


class CreateInterventionPlan(graphene.Mutation):
    class Arguments:
        patient_id = graphene.ID(required=True)
        created_by_id = graphene.ID(required=True)
        main_objective = graphene.String(required=True)
        start_date = graphene.Date(required=True)
        end_date = graphene.Date()

    plan = graphene.Field(InterventionPlanType)

    def mutate(self, info, patient_id, created_by_id, main_objective,
               start_date, end_date=None):
        plan = InterventionPlan.objects.create(
            patient_id=patient_id,
            created_by_id=created_by_id,
            main_objective=main_objective,
            start_date=start_date,
            end_date=end_date,
        )
        return CreateInterventionPlan(plan=plan)


class UpdatePlanProgress(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        progress_percent = graphene.Int(required=True)

    plan = graphene.Field(InterventionPlanType)

    def mutate(self, info, id, progress_percent):
        plan = InterventionPlan.objects.get(pk=id)
        plan.progress_percent = max(0, min(100, progress_percent))
        plan.save(update_fields=["progress_percent", "updated_at"])
        return UpdatePlanProgress(plan=plan)

class Mutation(graphene.ObjectType):
    create_patient = CreatePatient.Field()
    update_patient_status = UpdatePatientStatus.Field()
    add_clinical_note = AddClinicalNote.Field()
    create_intervention_plan = CreateInterventionPlan.Field()
    update_plan_progress = UpdatePlanProgress.Field()