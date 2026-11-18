import graphene

from config.utils import get_db_id, user_can_access_session

from .annotation_models import AnnotationCase
from .annotation_type import AnnotationCaseType


class AnnotationQuery(graphene.ObjectType):
    annotation_cases = graphene.List(
        AnnotationCaseType,
        run_id=graphene.ID(required=True),
        status=graphene.String(),
    )

    def resolve_annotation_cases(self, info, run_id, status=None):
        if not info.context.user.is_authenticated:
            return AnnotationCase.objects.none()
        try:
            run = AnnotationCase.objects.select_related("run__session").get(
                run_id=get_db_id(run_id)
            ).run
        except AnnotationCase.DoesNotExist:
            return AnnotationCase.objects.none()

        if not user_can_access_session(info.context.user, run.session_id):
            return AnnotationCase.objects.none()

        queryset = AnnotationCase.objects.filter(run=run).prefetch_related("reviews", "adjudication")
        if status:
            queryset = queryset.filter(status=status)
        return queryset
