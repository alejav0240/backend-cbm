import graphene

from clinical.models import Patient
from evaluations.models import ScaleEvaluationSubscaleResponse, ScaleEvaluationValueResponse, FormResponse, \
    ScaleEvaluation
from evaluations.type import ScaleEvaluationType, ScaleEvaluationSubscaleResponseType, ScaleEvaluationValueResponseType, \
    FormResponseType, FormAssignmentType


class CreateScaleEvaluation(graphene.Mutation):
    class Arguments:
        scale_id = graphene.ID(required=True)
        patient_id = graphene.ID(required=True)
        evaluator_id = graphene.ID(required=True)
        session_id = graphene.ID()
        notes = graphene.String()

    evaluation = graphene.Field(ScaleEvaluationType)

    def mutate(self, info, scale_id, patient_id, evaluator_id,
               session_id=None, notes=None):
        evaluation = ScaleEvaluation.objects.create(
            scale_id=scale_id,
            patient_id=patient_id,
            evaluator_id=evaluator_id,
            session_id=session_id,
            notes=notes,
        )
        return CreateScaleEvaluation(evaluation=evaluation)

class AddSubscaleResponse(graphene.Mutation):
    class Arguments:
        evaluation_id = graphene.ID(required=True)
        subscale_id = graphene.ID(required=True)
        score = graphene.Int(required=True)

    response = graphene.Field(ScaleEvaluationSubscaleResponseType)

    def mutate(self, info, evaluation_id, subscale_id, score):
        resp, _ = ScaleEvaluationSubscaleResponse.objects.update_or_create(
            evaluation_id=evaluation_id,
            subscale_id=subscale_id,
            defaults={"score": score},
        )
        return AddSubscaleResponse(response=resp)

class AddValueResponse(graphene.Mutation):
    class Arguments:
        evaluation_id = graphene.ID(required=True)
        scale_value_id = graphene.ID(required=True)

    response = graphene.Field(ScaleEvaluationValueResponseType)

    def mutate(self, info, evaluation_id, scale_value_id):
        resp, _ = ScaleEvaluationValueResponse.objects.get_or_create(
            evaluation_id=evaluation_id,
            scale_value_id=scale_value_id,
        )
        return AddValueResponse(response=resp)

class SubmitFormResponse(graphene.Mutation):
    class Arguments:
        assignment_id = graphene.ID(required=True)
        question_id = graphene.ID(required=True)
        response = graphene.String(required=True)

    form_response = graphene.Field(FormResponseType)

    def mutate(self, info, assignment_id, question_id, response):
        resp, _ = FormResponse.objects.update_or_create(
            assignment_id=assignment_id,
            question_id=question_id,
            defaults={"response": response},
        )
        return SubmitFormResponse(form_response=resp)

class DeletePatient(graphene.Mutation):
    class Arguments:
        # Usamos ID porque desde el front viene el Global ID de Relay
        id = graphene.ID(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, id):
        try:
            # graphene.relay.Node.get_node_from_global_id convierte
            # el Global ID (ej: "UGF0aWVudFR5cGU6MQ==") al objeto de Django
            patient = graphene.relay.Node.get_node_from_global_id(info, id, only_type=None)

            if not patient:
                # Si no es un Global ID, intentamos buscarlo por ID normal (opcional)
                patient = Patient.objects.get(pk=id)

            patient.delete()
            return DeletePatient(success=True, message="Paciente eliminado correctamente")

        except Patient.DoesNotExist:
            return DeletePatient(success=False, message="El paciente no existe")
        except Exception as e:
            return DeletePatient(success=False, message=str(e))

class ResponseInput(graphene.InputObjectType):
    question_id = graphene.ID(required=True)
    response = graphene.String(required=True)

class SubmitFullForm(graphene.Mutation):
    class Arguments:
        form_id = graphene.ID(required=True)
        assigned_to_id = graphene.ID(required=True) # El terapeuta
        assigned_by_id = graphene.ID(required=True) # Quien asigna (Admin)
        patient_id = graphene.ID(required=True)
        responses = graphene.List(ResponseInput, required=True)

    # Definimos qué devuelve la mutación
    assignment = graphene.Field(FormAssignmentType) # Asegúrate de tener este Type definido
    success = graphene.Boolean()

    def mutate(self, info, form_id, assigned_to_id, assigned_by_id, patient_id, responses):
        from evaluations.models import FormAssignment, FormResponse
        from django.db import transaction

        # Usamos una transacción atómica: si falla una respuesta, no se crea nada.
        with transaction.atomic():
            # 1. Crear la cabecera (La asignación)
            assignment = FormAssignment.objects.create(
                form_id=form_id,
                assigned_to_id=assigned_to_id,
                assigned_by_id=assigned_by_id,
                patient_id=patient_id
            )

            # 2. Crear todas las respuestas vinculadas a esta asignación
            for resp_data in responses:
                FormResponse.objects.create(
                    assignment=assignment,
                    question_id=resp_data.question_id,
                    response=resp_data.response
                )

        return SubmitFullForm(assignment=assignment, success=True)


class Mutation(graphene.ObjectType):
    create_scale_evaluation = CreateScaleEvaluation.Field()
    add_subscale_response = AddSubscaleResponse.Field()
    add_value_response = AddValueResponse.Field()
    submit_form_response = SubmitFormResponse.Field()
    submit_full_form = SubmitFullForm.Field()