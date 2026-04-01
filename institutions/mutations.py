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
            phone=phone,
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
        phone = graphene.String()

    def mutate(self, info, id, **kwargs):

        try:
            institution = Institution.objects.get(pk=id)
        except Institution.DoesNotExist:
            raise GraphQLError("Institución no encontrada")

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
            institution = Institution.objects.get(pk=id)
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
            institution = Institution.objects.get(pk=institution_id)
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
            group = InstitutionGroup.objects.get(pk=id)
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
            group = InstitutionGroup.objects.get(pk=id)
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