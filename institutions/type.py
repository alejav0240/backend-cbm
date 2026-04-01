from graphene_django import DjangoObjectType
from institutions.models import Institution, InstitutionGroup

class InstitutionType(DjangoObjectType):
    class Meta:
        model = Institution
        # "groups" funciona porque definiste related_name="groups" en InstitutionGroup
        fields = (
            "id",
            "name",
            "address",
            "contact_name",
            "contact_email",
            "contact_phone",
            "groups"
        )

class InstitutionGroupType(DjangoObjectType):
    class Meta:
        model = InstitutionGroup
        # "therapeutic_sessions" es el related_name que definiste en el modelo Session
        fields = (
            "id",
            "institution",
            "name",
            "description",
            "therapeutic_sessions"
        )