import graphene

from institutions.models import Institution, InstitutionGroup
from institutions.type import InstitutionType, InstitutionGroupType


class Query(graphene.ObjectType):
    institutions = graphene.List(InstitutionType)
    institution = graphene.Field(InstitutionType, id=graphene.ID(required=True))
    institution_groups = graphene.List(
        InstitutionGroupType,
        institution_id=graphene.ID(required=True),
    )

    def resolve_institutions(self, info):
        return Institution.objects.prefetch_related("groups").all()

    def resolve_institution(self, info, id):
        return Institution.objects.prefetch_related("groups").get(pk=id)

    def resolve_institution_groups(self, info, institution_id):
        return InstitutionGroup.objects.filter(institution_id=institution_id)