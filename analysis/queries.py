import graphene

from config.utils import get_db_id, user_can_access_session

from .models import ProcessingRun
from .type import ProcessingRunType


class Query(graphene.ObjectType):
    processing_runs = graphene.List(
        ProcessingRunType,
        session_id=graphene.ID(required=True),
        status=graphene.String(),
    )

    def resolve_processing_runs(self, info, session_id, status=None):
        if not info.context.user.is_authenticated:
            return ProcessingRun.objects.none()

        db_session_id = get_db_id(session_id)
        if not user_can_access_session(info.context.user, db_session_id):
            return ProcessingRun.objects.none()

        queryset = ProcessingRun.objects.filter(session_id=db_session_id).prefetch_related("artifacts")
        if status:
            queryset = queryset.filter(status=status)
        return queryset
