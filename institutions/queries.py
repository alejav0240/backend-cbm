import graphene
from institutions.models import Institution, InstitutionGroup
from institutions.type import InstitutionType, InstitutionGroupType, PaginatedInstitutions, PaginatedInstitutionGroups
from config.utils import module_permission_required, get_db_id

class Query(graphene.ObjectType):
    institutions = graphene.Field(
        PaginatedInstitutions,
        search=graphene.String(),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
    )
    institution = graphene.Field(InstitutionType, id=graphene.ID(required=True))
    institution_group = graphene.Field(InstitutionGroupType, id=graphene.ID(required=True))
    institution_groups = graphene.Field(
        PaginatedInstitutionGroups,
        institution_id=graphene.ID(required=True),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
    )

    @module_permission_required('instituciones', action='view')
    def resolve_institutions(self, info, search=None, page=1, page_size=10):
        qs = Institution.objects.prefetch_related("groups").all()
        if search:
            qs = qs.filter(name__icontains=search)
        total_count = qs.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        offset = (page - 1) * page_size
        return PaginatedInstitutions(
            results=qs[offset:offset + page_size],
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )

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
    def resolve_institution_groups(self, info, institution_id, page=1, page_size=10):
        real_inst_id = get_db_id(institution_id)
        qs = InstitutionGroup.objects.filter(institution_id=real_inst_id)
        total_count = qs.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        offset = (page - 1) * page_size
        return PaginatedInstitutionGroups(
            results=qs[offset:offset + page_size],
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )
