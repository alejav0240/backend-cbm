import graphene
from graphene_django import DjangoObjectType

from .models import Scale, Subscale, ScaleValue, ScaleEvaluation, ScaleEvaluationSubscaleResponse, \
    ScaleEvaluationValueResponse, Form, FormQuestion, FormAssignment, FormResponse


class ScaleType(DjangoObjectType):
    class Meta:
        model = Scale
        fields = ("id", "name", "description", "scale_type", "subscales", "values")


class SubscaleType(DjangoObjectType):
    class Meta:
        model = Subscale
        fields = ("id", "scale", "name", "description", "category", "max_value")


class ScaleValueType(DjangoObjectType):
    class Meta:
        model = ScaleValue
        fields = ("id", "scale", "label", "value")


class ScaleEvaluationType(DjangoObjectType):
    in_session = graphene.Boolean()
    total_score = graphene.Int()

    class Meta:
        model = ScaleEvaluation
        fields = (
            "id", "scale", "patient", "evaluator", "session",
            "evaluated_at",
            "subscale_responses", "value_responses",
        )

    def resolve_total_score(self, info):
        return self.total_score

    def resolve_in_session(self, info):
        return self.session_id is not None


class ScaleEvaluationSubscaleResponseType(DjangoObjectType):
    class Meta:
        model = ScaleEvaluationSubscaleResponse
        fields = ("id", "evaluation", "subscale", "score")


class ScaleEvaluationValueResponseType(DjangoObjectType):
    class Meta:
        model = ScaleEvaluationValueResponse
        fields = ("id", "evaluation", "scale_value")


class PaginatedScaleEvaluations(graphene.ObjectType):
    results = graphene.List(ScaleEvaluationType)
    total_count = graphene.Int()
    total_pages = graphene.Int()
    current_page = graphene.Int()


class FormType(DjangoObjectType):
    class Meta:
        model = Form
        fields = ("id", "name", "description", "questions", "assignments")


class FormQuestionType(DjangoObjectType):
    class Meta:
        model = FormQuestion
        fields = ("id", "form", "question", "question_type", "is_required", "order_index")


class FormAssignmentType(DjangoObjectType):
    completion_ratio = graphene.String()

    class Meta:
        model = FormAssignment
        fields = (
            "id", "form", "assigned_to", "assigned_by",
            "patient", "session", "created_at", "responses",
        )

    def resolve_completion_ratio(self, info):
        total = self.form.questions.count()
        answered = self.responses.count()
        return f"{answered}/{total}"


class FormResponseType(DjangoObjectType):
    class Meta:
        model = FormResponse
        fields = ("id", "assignment", "question", "response", "responded_at")
