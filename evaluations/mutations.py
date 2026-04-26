import graphene
from django.db import transaction
from clinical.models import Patient
from evaluations.models import (
    ScaleEvaluationSubscaleResponse, 
    ScaleEvaluationValueResponse, 
    FormResponse, 
    ScaleEvaluation, 
    FormAssignment,
    Subscale,
    ScaleValue
)
from evaluations.type import (
    ScaleEvaluationType, 
    FormResponseType, 
    FormAssignmentType
)

class SubmitFormResponse(graphene.Mutation):
    class Arguments:
        assignment_id = graphene.ID(required=True)
        question_id = graphene.ID(required=True)
        response = graphene.String(required=True)

    form_response = graphene.Field(FormResponseType)

    def mutate(self, info, assignment_id, question_id, response):
        try:
            real_assignment_id = int(graphene.relay.Node.from_global_id(assignment_id)[1])
        except:
            real_assignment_id = assignment_id

        try:
            real_question_id = int(graphene.relay.Node.from_global_id(question_id)[1])
        except:
            real_question_id = question_id

        resp, _ = FormResponse.objects.update_or_create(
            assignment_id=real_assignment_id,
            question_id=real_question_id,
            defaults={"response": response},
        )
        return SubmitFormResponse(form_response=resp)

class ResponseInput(graphene.InputObjectType):
    question_id = graphene.ID(required=True)
    response = graphene.String(required=True)

class SubmitFullForm(graphene.Mutation):
    class Arguments:
        form_id = graphene.ID(required=True)
        assigned_to_id = graphene.ID(required=True)
        assigned_by_id = graphene.ID(required=True)
        patient_id = graphene.ID(required=True)
        responses = graphene.List(ResponseInput, required=True)

    assignment = graphene.Field(FormAssignmentType)
    success = graphene.Boolean()

    @transaction.atomic
    def mutate(self, info, form_id, assigned_to_id, assigned_by_id, patient_id, responses):
        try:
            real_form_id = int(graphene.relay.Node.from_global_id(form_id)[1])
        except:
            real_form_id = form_id

        try:
            real_assigned_to_id = int(graphene.relay.Node.from_global_id(assigned_to_id)[1])
        except:
            real_assigned_to_id = assigned_to_id

        try:
            real_assigned_by_id = int(graphene.relay.Node.from_global_id(assigned_by_id)[1])
        except:
            real_assigned_by_id = assigned_by_id

        try:
            real_patient_id = int(graphene.relay.Node.from_global_id(patient_id)[1])
        except:
            real_patient_id = patient_id

        assignment = FormAssignment.objects.create(
            form_id=real_form_id,
            assigned_to_id=real_assigned_to_id,
            assigned_by_id=real_assigned_by_id,
            patient_id=real_patient_id
        )

        for resp_data in responses:
            try:
                real_resp_question_id = int(graphene.relay.Node.from_global_id(resp_data.question_id)[1])
            except:
                real_resp_question_id = resp_data.question_id

            FormResponse.objects.create(
                assignment=assignment,
                question_id=real_resp_question_id,
                response=resp_data.response
            )

        return SubmitFullForm(assignment=assignment, success=True)

class ResponseSubScale(graphene.InputObjectType):
    subscale_id = graphene.ID(required=True)
    score = graphene.Int(required=True)

class AddScaleResponse(graphene.Mutation):
    class Arguments:
        patient_id = graphene.ID(required=True)
        evaluator_id = graphene.ID(required=True)
        scale_id = graphene.ID(required=True)
        session_id = graphene.ID()
        subscales = graphene.List(ResponseSubScale)
        scale_value = graphene.ID()

    success = graphene.Boolean()
    message = graphene.String()

    @transaction.atomic
    def mutate(self, info, patient_id, evaluator_id, scale_id, session_id=None, subscales=None, scale_value=None):
        try:
            # Manejar IDs de Relay
            try:
                real_patient_id = int(graphene.relay.Node.from_global_id(patient_id)[1])
            except:
                real_patient_id = patient_id

            try:
                real_evaluator_id = int(graphene.relay.Node.from_global_id(evaluator_id)[1])
            except:
                real_evaluator_id = evaluator_id

            try:
                real_scale_id = int(graphene.relay.Node.from_global_id(scale_id)[1])
            except:
                real_scale_id = scale_id

            real_session_id = None
            if session_id:
                try:
                    real_session_id = int(graphene.relay.Node.from_global_id(session_id)[1])
                except:
                    real_session_id = session_id

            # 1. Crear o recuperar la evaluación principal
            evaluation, created = ScaleEvaluation.objects.update_or_create(
                patient_id=real_patient_id,
                scale_id=real_scale_id,
                session_id=real_session_id,
                defaults={'evaluator_id': real_evaluator_id}
            )

            # 2. Procesar respuestas por SUBESCALAS con validación
            if subscales:
                valid_subscale_ids = set(Subscale.objects.filter(scale_id=real_scale_id).values_list('id', flat=True))
                
                for item in subscales:
                    try:
                        real_subscale_id = int(graphene.relay.Node.from_global_id(item.subscale_id)[1])
                    except:
                        real_subscale_id = item.subscale_id

                    if int(real_subscale_id) not in valid_subscale_ids:
                        raise Exception(f"La subescala {real_subscale_id} no pertenece a la escala seleccionada.")
                    
                    ScaleEvaluationSubscaleResponse.objects.update_or_create(
                        evaluation=evaluation,
                        subscale_id=real_subscale_id,
                        defaults={'score': item.score}
                    )

            # 3. Procesar respuestas por LISTA DE VALORES con validación
            if scale_value:
                try:
                    real_scale_value_id = int(graphene.relay.Node.from_global_id(scale_value)[1])
                except:
                    real_scale_value_id = scale_value

                if not ScaleValue.objects.filter(id=real_scale_value_id, scale_id=real_scale_id).exists():
                    raise Exception(f"El valor {real_scale_value_id} no pertenece a la escala seleccionada.")
                
                ScaleEvaluationValueResponse.objects.get_or_create(
                    evaluation=evaluation,
                    scale_value_id=real_scale_value_id
                )

            return AddScaleResponse(success=True, message="Evaluación guardada correctamente")

        except Exception as e:
            return AddScaleResponse(success=False, message=str(e))

class Mutation(graphene.ObjectType):
    submit_form_response = SubmitFormResponse.Field()
    submit_full_form = SubmitFullForm.Field()
    add_scale_response = AddScaleResponse.Field()
