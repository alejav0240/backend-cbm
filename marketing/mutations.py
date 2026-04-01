import graphene

from marketing.models import MarketingCampaign, Lead
from marketing.type import MarketingCampaignType, LeadType


class CreateLead(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        phone = graphene.String()
        email = graphene.String()
        campaign_id = graphene.ID()

    lead = graphene.Field(LeadType)

    def mutate(self, info, name, phone=None, email=None, campaign_id=None):
        lead = Lead.objects.create(
            name=name,
            phone=phone,
            email=email,
            campaign_id=campaign_id,
        )
        return CreateLead(lead=lead)


class UpdateLeadStatus(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        status = graphene.String(required=True)

    lead = graphene.Field(LeadType)

    def mutate(self, info, id, status):
        lead = Lead.objects.get(pk=id)
        lead.status = status
        lead.save(update_fields=["status", "updated_at"])
        return UpdateLeadStatus(lead=lead)


class UpdateCampaignSpent(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        spent = graphene.Float(required=True)

    campaign = graphene.Field(MarketingCampaignType)

    def mutate(self, info, id, spent):
        campaign = MarketingCampaign.objects.get(pk=id)
        campaign.spent = spent
        campaign.save(update_fields=["spent", "updated_at"])
        return UpdateCampaignSpent(campaign=campaign)

class Mutation(graphene.ObjectType):
    create_lead = CreateLead.Field()
    update_lead_status = UpdateLeadStatus.Field()
    update_campaign_spent = UpdateCampaignSpent.Field()