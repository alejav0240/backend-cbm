import graphene

from institutions.models import Institution, InstitutionGroup
from institutions.type import InstitutionType, InstitutionGroupType


class Query(graphene.ObjectType):
    institutions = graphene.List(InstitutionType)
    institution = graphene.Field(InstitutionType, id=graphene.ID(required=True))
    institution_group = graphene.Field(InstitutionGroupType, id=graphene.ID(required=True))
    institution_groups = graphene.List(
        InstitutionGroupType,
        institution_id=graphene.ID(required=True),
    )

    def resolve_institutions(self, info):
        return Institution.objects.prefetch_related("groups").all()

    def resolve_institution(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        return Institution.objects.prefetch_related("groups").get(pk=real_id)

    def resolve_institution_group(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        return InstitutionGroup.objects.prefetch_related(
            "therapeutic_sessions__therapist"
        ).get(pk=real_id)

    def resolve_institution_groups(self, info, institution_id):
        try:
            real_inst_id = int(graphene.relay.Node.from_global_id(institution_id)[1])
        except:
            real_inst_id = institution_id
        return InstitutionGroup.objects.filter(institution_id=real_inst_id)