import graphene
from django.db import transaction
from graphql import GraphQLError
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
from config.utils import module_permission_required, get_db_id

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

    @module_permission_required('formularios', action='add')
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

    @module_permission_required('formularios', action='delete')
    def mutate(self, info, id):
        real_id = get_db_id(id)
        try:
            form = Form.objects.get(pk=real_id)
            form.delete()
            return DeleteForm(success=True)
        except Form.DoesNotExist:
            return DeleteForm(success=False)

class AssignForm(graphene.Mutation):
    class Arguments:
        form_id = graphene.ID(required=True)
        assigned_by_id = graphene.ID(required=True)
        assigned_to_id = graphene.ID()
        patient_id = graphene.ID()
        session_id = graphene.ID()

    assignment = graphene.Field(FormAssignmentType)

    @module_permission_required('formularios', action='add')
    def mutate(self, info, form_id, assigned_by_id, assigned_to_id=None,
               patient_id=None, session_id=None):
        try:
            assignment = FormAssignment.objects.create(
                form_id=get_db_id(form_id),
                assigned_by_id=get_db_id(assigned_by_id),
                assigned_to_id=get_db_id(assigned_to_id),
                patient_id=get_db_id(patient_id),
                session_id=get_db_id(session_id),
            )
            return AssignForm(assignment=assignment)
        except Exception as e:
            raise GraphQLError(str(e))


class UpdateFormAssignment(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        assigned_to_id = graphene.ID()
        patient_id = graphene.ID()
        session_id = graphene.ID()

    assignment = graphene.Field(FormAssignmentType)

    @module_permission_required('formularios', action='change')
    def mutate(self, info, id, assigned_to_id=None, patient_id=None, session_id=None):
        real_id = get_db_id(id)
        try:
            assignment = FormAssignment.objects.get(pk=real_id)
            if assigned_to_id is not None:
                assignment.assigned_to_id = get_db_id(assigned_to_id)
            if patient_id is not None:
                assignment.patient_id = get_db_id(patient_id)
            if session_id is not None:
                assignment.session_id = get_db_id(session_id)
            assignment.save()
            return UpdateFormAssignment(assignment=assignment)
        except FormAssignment.DoesNotExist:
            raise GraphQLError("Asignación no encontrada")


class DeleteFormAssignment(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    success = graphene.Boolean()

    @module_permission_required('formularios', action='delete')
    def mutate(self, info, id):
        real_id = get_db_id(id)
        try:
            FormAssignment.objects.get(pk=real_id).delete()
            return DeleteFormAssignment(success=True)
        except FormAssignment.DoesNotExist:
            return DeleteFormAssignment(success=False)

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

    @module_permission_required('escalas', action='add')
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

    @module_permission_required('escalas', action='delete')
    def mutate(self, info, id):
        real_id = get_db_id(id)
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
        real_assignment_id = get_db_id(assignment_id)
        real_question_id = get_db_id(question_id)

        try:
            response, created = FormResponse.objects.update_or_create(
                assignment_id=real_assignment_id,
                question_id=real_question_id,
                defaults={'response': response_text}
            )
            return SubmitFormResponse(success=True, response=response)
        except Exception as e:
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
        real_assignment_id = get_db_id(assignment_id)

        try:
            assignment = FormAssignment.objects.get(pk=real_assignment_id)
            
            with transaction.atomic():
                for resp in responses:
                    real_q_id = get_db_id(resp.question_id)
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
        subscales = graphene.List(ResponseSubScale)
        value_id = graphene.ID()

    success = graphene.Boolean()
    message = graphene.String()

    @module_permission_required('evaluaciones', action='add')
    def mutate(self, info, patient_id, evaluator_id, scale_id, 
               session_id=None, subscales=None, value_id=None):
        
        try:
            real_patient_id = get_db_id(patient_id)
            real_evaluator_id = get_db_id(evaluator_id)
            real_scale_id = get_db_id(scale_id)
            real_session_id = get_db_id(session_id)

            with transaction.atomic():
                evaluation = ScaleEvaluation.objects.create(
                    patient_id=real_patient_id,
                    evaluator_id=real_evaluator_id,
                    scale_id=real_scale_id,
                    session_id=real_session_id
                )

                if subscales:
                    for sub in subscales:
                        real_sub_id = get_db_id(sub.subscale_id)
                        ScaleEvaluationSubscaleResponse.objects.create(
                            evaluation=evaluation,
                            subscale_id=real_sub_id,
                            score=sub.score
                        )
                
                if value_id:
                    real_value_id = get_db_id(value_id)
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
    update_form_assignment = UpdateFormAssignment.Field()
    delete_form_assignment = DeleteFormAssignment.Field()
