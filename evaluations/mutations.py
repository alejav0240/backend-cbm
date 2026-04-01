import graphene

from evaluations.models import ScaleEvaluationSubscaleResponse, ScaleEvaluationValueResponse, FormResponse, \
    ScaleEvaluation
from evaluations.type import ScaleEvaluationType, ScaleEvaluationSubscaleResponseType, ScaleEvaluationValueResponseType, \
    FormResponseType


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


class Mutation(graphene.ObjectType):
    create_scale_evaluation = CreateScaleEvaluation.Field()
    add_subscale_response = AddSubscaleResponse.Field()
    add_value_response = AddValueResponse.Field()
    submit_form_response = SubmitFormResponse.Field()