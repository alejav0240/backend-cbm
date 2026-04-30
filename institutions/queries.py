import graphene

from institutions.models import Institution, InstitutionGroup
from institutions.type import InstitutionType, InstitutionGroupType


def get_real_id(id_attr):
    if not id_attr:
        return None

    # Si ya es un entero o parece serlo, no decodificamos
    if isinstance(id_attr, int) or (isinstance(id_attr, str) and id_attr.isdigit()):
        return id_attr

    try:
        # Intentar decodificación manual de Relay (Base64)
        # Relay IDs suelen ser "Tipo:ID" codificados en Base64
        decoded = base64.b64decode(str(id_attr)).decode('utf-8')
        if ":" in decoded:
            return decoded.split(":")[1]
        return decoded
    except Exception:
        # Si falla el Base64, intentar el helper de Graphene por si acaso
        try:
            from graphql_relay import from_global_id
            return from_global_id(id_attr)[1]
        except Exception:
            # Si todo falla, devolver el original
            return id_attr

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
            real_id = get_real_id(id)
        except:
            real_id = id
        return Institution.objects.prefetch_related("groups").get(pk=real_id)

    def resolve_institution_group(self, info, id):
        try:
            real_id = get_real_id(id)
        except:
            real_id = id
        return InstitutionGroup.objects.prefetch_related(
            "therapeutic_sessions__therapist"
        ).get(pk=real_id)

    def resolve_institution_groups(self, info, institution_id):
        try:
            real_inst_id = get_real_id(institution_id)
        except:
            real_inst_id = institution_id
        return InstitutionGroup.objects.filter(institution_id=real_inst_id)