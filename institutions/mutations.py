import graphene
from graphql import GraphQLError

from institutions.models import Institution, InstitutionGroup
from institutions.type import InstitutionType, InstitutionGroupType


# -----------------------------
# CREATE INSTITUTION
# -----------------------------
class CreateInstitution(graphene.Mutation):

    institution = graphene.Field(InstitutionType)

    class Arguments:
        name = graphene.String(required=True)
        contact_email = graphene.String()
        phone = graphene.String()

    def mutate(self, info, name, contact_email=None, phone=None):

        if Institution.objects.filter(name=name).exists():
            raise GraphQLError("Ya existe una institución con ese nombre")

        institution = Institution.objects.create(
            name=name,
            contact_email=contact_email,
            contact_phone=phone,
        )

        return CreateInstitution(institution=institution)


# -----------------------------
# UPDATE INSTITUTION
# -----------------------------
class UpdateInstitution(graphene.Mutation):

    institution = graphene.Field(InstitutionType)

    class Arguments:
        id = graphene.ID(required=True)
        name = graphene.String()
        contact_email = graphene.String()
        phone = graphene.String() # Recibimos 'phone' desde el front

    def mutate(self, info, id, **kwargs):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
            
        try:
            institution = Institution.objects.get(pk=real_id)
        except Institution.DoesNotExist:
            raise GraphQLError("Institución no encontrada")

        if "phone" in kwargs:
            institution.contact_phone = kwargs.pop("phone")

        for field, value in kwargs.items():
            setattr(institution, field, value)

        institution.save()
        return UpdateInstitution(institution=institution)


# -----------------------------
# DELETE INSTITUTION
# -----------------------------
class DeleteInstitution(graphene.Mutation):

    success = graphene.Boolean()

    class Arguments:
        id = graphene.ID(required=True)

    def mutate(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id

        try:
            institution = Institution.objects.get(pk=real_id)
        except Institution.DoesNotExist:
            raise GraphQLError("Institución no encontrada")

        institution.delete()

        return DeleteInstitution(success=True)


# -----------------------------
# CREATE GROUP
# -----------------------------
class CreateInstitutionGroup(graphene.Mutation):

    group = graphene.Field(InstitutionGroupType)

    class Arguments:
        institution_id = graphene.ID(required=True)
        name = graphene.String(required=True)

    def mutate(self, info, institution_id, name):
        try:
            real_inst_id = int(graphene.relay.Node.from_global_id(institution_id)[1])
        except:
            real_inst_id = institution_id

        try:
            institution = Institution.objects.get(pk=real_inst_id)
        except Institution.DoesNotExist:
            raise GraphQLError("Institución no encontrada")

        group = InstitutionGroup.objects.create(
            institution=institution,
            name=name,
        )

        return CreateInstitutionGroup(group=group)


# -----------------------------
# UPDATE GROUP
# -----------------------------
class UpdateInstitutionGroup(graphene.Mutation):

    group = graphene.Field(InstitutionGroupType)

    class Arguments:
        id = graphene.ID(required=True)
        name = graphene.String()

    def mutate(self, info, id, name=None):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id

        try:
            group = InstitutionGroup.objects.get(pk=real_id)
        except InstitutionGroup.DoesNotExist:
            raise GraphQLError("Grupo no encontrado")

        if name:
            group.name = name

        group.save()

        return UpdateInstitutionGroup(group=group)


# -----------------------------
# DELETE GROUP
# -----------------------------
class DeleteInstitutionGroup(graphene.Mutation):

    success = graphene.Boolean()

    class Arguments:
        id = graphene.ID(required=True)

    def mutate(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id

        try:
            group = InstitutionGroup.objects.get(pk=real_id)
        except InstitutionGroup.DoesNotExist:
            raise GraphQLError("Grupo no encontrado")

        group.delete()

        return DeleteInstitutionGroup(success=True)


# -----------------------------
# ROOT MUTATIONS
# -----------------------------
class Mutation(graphene.ObjectType):

    create_institution = CreateInstitution.Field()
    update_institution = UpdateInstitution.Field()
    delete_institution = DeleteInstitution.Field()

    create_institution_group = CreateInstitutionGroup.Field()
    update_institution_group = UpdateInstitutionGroup.Field()
    delete_institution_group = DeleteInstitutionGroup.Field()