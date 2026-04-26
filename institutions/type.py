from graphene_django import DjangoObjectType
import graphene
from institutions.models import Institution, InstitutionGroup
from therapeutic_sessions.type import SessionType

class InstitutionGroupType(DjangoObjectType):
    # Forzamos a que therapeutic_sessions sea una lista plana, no una Connection de Relay
    therapeutic_sessions = graphene.List(SessionType)

    class Meta:
        model = InstitutionGroup
        fields = (
            "id",
            "institution",
            "name",
            "description",
            "therapeutic_sessions"
        )
        interfaces = (graphene.relay.Node,)

    def resolve_therapeutic_sessions(self, info):
        return self.therapeutic_sessions.all()

class InstitutionType(DjangoObjectType):
    # Forzamos a que groups sea una lista plana, no una Connection de Relay
    groups = graphene.List(InstitutionGroupType)

    class Meta:
        model = Institution
        fields = (
            "id",
            "name",
            "address",
            "contact_name",
            "contact_email",
            "contact_phone",
            "groups"
        )
        interfaces = (graphene.relay.Node,)
        
    def resolve_groups(self, info):
        return self.groups.all()
