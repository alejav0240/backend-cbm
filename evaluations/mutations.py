import graphene
from django.db import transaction
from clinical.models import Patient
from users.models import User
from evaluations.models import (
    ScaleEvaluationSubscaleResponse, 
    ScaleEvaluationValueResponse, 
    FormResponse, 
    ScaleEvaluation, 
    FormAssignment,
    Subscale,
    ScaleValue,
    Scale,
    Form,
    FormQuestion
)
from evaluations.type import (
    ScaleEvaluationType, 
    FormResponseType, 
    FormAssignmentType,
    ScaleType,
    FormType
)

class QuestionInput(graphene.InputObjectType):
    question = graphene.String(required=True)
    question_type = graphene.String(required=True)
    is_required = graphene.Boolean()
    order_index = graphene.Int()

class CreateForm(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        description = graphene.String()
        questions = graphene.List(QuestionInput, required=True)

    form = graphene.Field(FormType)

    def mutate(self, info, name, questions, description=None):
        with transaction.atomic():
            form = Form.objects.create(name=name, description=description)
            for idx, q in enumerate(questions):
                FormQuestion.objects.create(
                    form=form,
                    question=q.question,
                    question_type=q.question_type,
                    is_required=q.is_required if q.is_required is not None else True,
                    order_index=q.order_index if q.order_index is not None else idx
                )
        return CreateForm(form=form)

class DeleteForm(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    success = graphene.Boolean()

    def mutate(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        try:
            form = Form.objects.get(pk=real_id)
            form.delete()
            return DeleteForm(success=True)
        except Form.DoesNotExist:
            return DeleteForm(success=False)

class AssignForm(graphene.Mutation):
    class Arguments:
        form_id = graphene.ID(required=True)
        assigned_to_id = graphene.ID(required=True)
        assigned_by_id = graphene.ID(required=True)
        patient_id = graphene.ID()

    assignment = graphene.Field(FormAssignmentType)

    def mutate(self, info, form_id, assigned_to_id, assigned_by_id, patient_id=None):
        def get_real_id(gid):
            if not gid: return None
            try:
                return int(graphene.relay.Node.from_global_id(gid)[1])
            except:
                return gid
        
        real_form_id = get_real_id(form_id)
        real_to_id = get_real_id(assigned_to_id)
        real_by_id = get_real_id(assigned_by_id)
        real_patient_id = get_real_id(patient_id)

        try:
            assignment = FormAssignment.objects.create(
                form_id=real_form_id,
                assigned_to_id=real_to_id,
                assigned_by_id=real_by_id,
                patient_id=real_patient_id
            )
            return AssignForm(assignment=assignment)
        except Exception as e:
            raise GraphQLError(str(e))

class SubscaleInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    description = graphene.String()
    max_value = graphene.Int(required=True)

class ScaleValueInput(graphene.InputObjectType):
    label = graphene.String(required=True)
    value = graphene.Int(required=True)

class CreateScale(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        description = graphene.String()
        scale_type = graphene.String(required=True)
        subscales = graphene.List(SubscaleInput)
        values = graphene.List(ScaleValueInput)

    scale = graphene.Field(ScaleType)

    def mutate(self, info, name, scale_type, description=None, subscales=None, values=None):
        with transaction.atomic():
            scale = Scale.objects.create(
                name=name,
                description=description,
                scale_type=scale_type
            )

            if scale_type == Scale.ScaleType.SUBSCALE and subscales:
                for sub in subscales:
                    Subscale.objects.create(
                        scale=scale,
                        name=sub.name,
                        description=sub.description,
                        max_value=sub.max_value
                    )
            elif scale_type == Scale.ScaleType.VALUE_LIST and values:
                for val in values:
                    ScaleValue.objects.create(
                        scale=scale,
                        label=val.label,
                        value=val.value
                    )
        return CreateScale(scale=scale)

class DeleteScale(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    success = graphene.Boolean()

    def mutate(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        try:
            scale = Scale.objects.get(pk=real_id)
            scale.delete()
            return DeleteScale(success=True)
        except Scale.DoesNotExist:
            return DeleteScale(success=False)

class SubmitFormResponse(graphene.Mutation):
    class Arguments:
        assignment_id = graphene.ID(required=True)
        question_id = graphene.ID(required=True)
        response_text = graphene.String(required=True)

    success = graphene.Boolean()
    response = graphene.Field(FormResponseType)

    def mutate(self, info, assignment_id, question_id, response_text):
        # Resolver IDs si vienen de Relay (GraphQL Global ID)
        try:
            real_assignment_id = int(graphene.relay.Node.from_global_id(assignment_id)[1])
        except:
            real_assignment_id = assignment_id
            
        try:
            real_question_id = int(graphene.relay.Node.from_global_id(question_id)[1])
        except:
            real_question_id = question_id

        try:
            # Usar update_or_create para permitir sobrescribir una respuesta anterior
            response, created = FormResponse.objects.update_or_create(
                assignment_id=real_assignment_id,
                question_id=real_question_id,
                defaults={'response': response_text}
            )
            return SubmitFormResponse(success=True, response=response)
        except Exception as e:
            # Puedes loguear el error 'e' aquí si es necesario
            return SubmitFormResponse(success=False, response=None)


class ResponseInput(graphene.InputObjectType):
    question_id = graphene.ID(required=True)
    response_text = graphene.String(required=True)

class SubmitFullForm(graphene.Mutation):
    class Arguments:
        assignment_id = graphene.ID(required=True)
        responses = graphene.List(ResponseInput, required=True)

    success = graphene.Boolean()
    assignment = graphene.Field(FormAssignmentType)

    def mutate(self, info, assignment_id, responses):
        try:
            real_assignment_id = int(graphene.relay.Node.from_global_id(assignment_id)[1])
        except:
            real_assignment_id = assignment_id

        try:
            assignment = FormAssignment.objects.get(pk=real_assignment_id)
            
            with transaction.atomic():
                for resp in responses:
                    try:
                        real_q_id = int(graphene.relay.Node.from_global_id(resp.question_id)[1])
                    except:
                        real_q_id = resp.question_id
                        
                    FormResponse.objects.update_or_create(
                        assignment=assignment,
                        question_id=real_q_id,
                        defaults={'response': resp.response_text}
                    )
            return SubmitFullForm(success=True, assignment=assignment)
        except FormAssignment.DoesNotExist:
            return SubmitFullForm(success=False, assignment=None)
        except Exception as e:
            return SubmitFullForm(success=False, assignment=None)

class ResponseSubScale(graphene.InputObjectType):
    subscale_id = graphene.ID(required=True)
    score = graphene.Int(required=True)

class AddScaleResponse(graphene.Mutation):
    class Arguments:
        patient_id = graphene.ID(required=True)
        evaluator_id = graphene.ID(required=True)
        scale_id = graphene.ID(required=True)
        session_id = graphene.ID()
        # Se envía lista de subescalas si la escala es tipo SUBSCALE
        subscales = graphene.List(ResponseSubScale)
        # Se envía un solo valor_id si la escala es VALUE_LIST
        value_id = graphene.ID()

    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, patient_id, evaluator_id, scale_id, 
               session_id=None, subscales=None, value_id=None):
        
        # Desempaquetar IDs si es necesario (Relay)
        def get_real_id(gid):
            if not gid: return None
            try:
                return int(graphene.relay.Node.from_global_id(gid)[1])
            except:
                return gid

        try:
            real_patient_id = get_real_id(patient_id)
            real_evaluator_id = get_real_id(evaluator_id)
            real_scale_id = get_real_id(scale_id)
            real_session_id = get_real_id(session_id)

            with transaction.atomic():
                evaluation = ScaleEvaluation.objects.create(
                    patient_id=real_patient_id,
                    evaluator_id=real_evaluator_id,
                    scale_id=real_scale_id,
                    session_id=real_session_id
                )

                if subscales:
                    for sub in subscales:
                        real_sub_id = get_real_id(sub.subscale_id)
                        ScaleEvaluationSubscaleResponse.objects.create(
                            evaluation=evaluation,
                            subscale_id=real_sub_id,
                            score=sub.score
                        )
                
                if value_id:
                    real_value_id = get_real_id(value_id)
                    ScaleEvaluationValueResponse.objects.create(
                        evaluation=evaluation,
                        scale_value_id=real_value_id
                    )

            return AddScaleResponse(success=True, message="Evaluación guardada correctamente")

        except Exception as e:
            return AddScaleResponse(success=False, message=str(e))

class Mutation(graphene.ObjectType):
    submit_form_response = SubmitFormResponse.Field()
    submit_full_form = SubmitFullForm.Field()
    add_scale_response = AddScaleResponse.Field()
    create_scale = CreateScale.Field()
    delete_scale = DeleteScale.Field()
    create_form = CreateForm.Field()
    delete_form = DeleteForm.Field()
    assign_form = AssignForm.Field()
