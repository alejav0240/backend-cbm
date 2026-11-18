from .annotation_mutations import AnnotationMutation
from .annotation_queries import AnnotationQuery
from .mutations import Mutation as ProcessingMutation
from .queries import Query as ProcessingQuery


class Query(AnnotationQuery, ProcessingQuery):
    pass


class Mutation(AnnotationMutation, ProcessingMutation):
    pass


__all__ = ["Query", "Mutation"]
