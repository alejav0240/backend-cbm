import graphene
from decimal import Decimal
from graphql import GraphQLError
from marketing.models import MarketingCampaign, Lead
from marketing.type import MarketingCampaignType, LeadType

class CreateCampaign(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        platform = graphene.String(required=True)
        budget = graphene.Float(required=True)
        status = graphene.String()

    campaign = graphene.Field(MarketingCampaignType)

    def mutate(self, info, name, platform, budget, status="draft"):
        campaign = MarketingCampaign.objects.create(
            name=name,
            platform=platform,
            budget=Decimal(str(budget)),
            status=status
        )
        return CreateCampaign(campaign=campaign)

class CreateLead(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        phone = graphene.String()
        email = graphene.String()
        campaign_id = graphene.ID()

    lead = graphene.Field(LeadType)

    def mutate(self, info, name, phone=None, email=None, campaign_id=None):
        real_campaign_id = None
        if campaign_id:
            try:
                real_campaign_id = int(graphene.relay.Node.from_global_id(campaign_id)[1])
            except:
                real_campaign_id = campaign_id

        lead = Lead.objects.create(
            name=name,
            phone=phone,
            email=email,
            campaign_id=real_campaign_id,
        )
        return CreateLead(lead=lead)

class UpdateLeadStatus(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        status = graphene.String(required=True)

    lead = graphene.Field(LeadType)

    def mutate(self, info, id, status):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id

        try:
            lead = Lead.objects.get(pk=real_id)
        except Lead.DoesNotExist:
            raise GraphQLError("Lead no encontrado")

        lead.status = status
        lead.save(update_fields=["status", "updated_at"])
        return UpdateLeadStatus(lead=lead)

class UpdateCampaignSpent(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        spent = graphene.Float(required=True)

    campaign = graphene.Field(MarketingCampaignType)

    def mutate(self, info, id, spent):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id

        try:
            campaign = MarketingCampaign.objects.get(pk=real_id)
        except MarketingCampaign.DoesNotExist:
            raise GraphQLError("Campaña no encontrada")

        # Convertimos a Decimal para mantener precisión financiera
        campaign.spent = Decimal(str(spent))
        campaign.save(update_fields=["spent", "updated_at"])
        return UpdateCampaignSpent(campaign=campaign)

class Mutation(graphene.ObjectType):
    create_campaign = CreateCampaign.Field()
    create_lead = CreateLead.Field()
    update_lead_status = UpdateLeadStatus.Field()
    update_campaign_spent = UpdateCampaignSpent.Field()
