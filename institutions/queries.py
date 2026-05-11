import graphene
from institutions.models import Institution, InstitutionGroup
from institutions.type import InstitutionType, InstitutionGroupType
from config.utils import module_permission_required, get_db_id

class Query(graphene.ObjectType):
    institutions = graphene.List(InstitutionType)
    institution = graphene.Field(InstitutionType, id=graphene.ID(required=True))
    institution_group = graphene.Field(InstitutionGroupType, id=graphene.ID(required=True))
    institution_groups = graphene.List(
        InstitutionGroupType,
        institution_id=graphene.ID(required=True),
    )

    @module_permission_required('instituciones', action='view')
    def resolve_institutions(self, info):
        return Institution.objects.prefetch_related("groups").all()

    @module_permission_required('instituciones', action='view')
    def resolve_institution(self, info, id):
        real_id = get_db_id(id)
        return Institution.objects.prefetch_related("groups").get(pk=real_id)

    @module_permission_required('instituciones', action='view')
    def resolve_institution_group(self, info, id):
        real_id = get_db_id(id)
        return InstitutionGroup.objects.prefetch_related(
            "therapeutic_sessions__therapist"
        ).get(pk=real_id)

    @module_permission_required('instituciones', action='view')
    def resolve_institution_groups(self, info, institution_id):
        real_inst_id = get_db_id(institution_id)
        return InstitutionGroup.objects.filter(institution_id=real_inst_id)
