import graphene
from users.schema import Query as UsersQuery, Mutation as UsersMutation
from therapeutic_sessions.schema import Query as SessionQuery, Mutation as SessionMutation
from institutions.schema import Query as InstitutionsQuery, Mutation as InstitutionsMutation
from finance.schema import Query as FinanceQuery, Mutation as FinanceMutation
from evaluations.schema import Query as EvaluationsQuery, Mutation as EvaluationsMutation
from clinical.schema import Query as ClinicalQuery, Mutation as ClinicalMutation
from marketing.schema import Query as MarketingQuery, Mutation as MarketingMutation
from uploads.schema import Mutation as UploadsMutation
from .stats import Query as StatsQuery
from analysis.schema import Query as AnalysisQuery, Mutation as AnalysisMutation

class Query(
    UsersQuery,
    SessionQuery,
    MarketingQuery,
    InstitutionsQuery,
    FinanceQuery,
    EvaluationsQuery,
    ClinicalQuery,
    StatsQuery,
    AnalysisQuery,
    graphene.ObjectType
):
    pass

class Mutation(
    UsersMutation,
    SessionMutation,
    MarketingMutation,
    InstitutionsMutation,
    FinanceMutation,
    EvaluationsMutation,
    ClinicalMutation,
    UploadsMutation,
    AnalysisMutation,
    graphene.ObjectType
):
    pass

schema = graphene.Schema(query=Query, mutation=Mutation)