import graphene

from marketing.models import MarketingCampaign, Lead
from marketing.type import MarketingCampaignType, LeadType


class Query(graphene.ObjectType):
    marketing_campaigns = graphene.List(
        MarketingCampaignType,
        status=graphene.String(),
        platform=graphene.String(),
    )
    marketing_campaign = graphene.Field(MarketingCampaignType, id=graphene.ID(required=True))

    leads = graphene.List(
        LeadType,
        campaign_id=graphene.ID(),
        status=graphene.String(),
    )
    lead = graphene.Field(LeadType, id=graphene.ID(required=True))

    def resolve_marketing_campaigns(self, info, status=None, platform=None):
        qs = MarketingCampaign.objects.prefetch_related("leads").all()
        if status:
            qs = qs.filter(status=status)
        if platform:
            qs = qs.filter(platform__icontains=platform)
        return qs

    def resolve_marketing_campaign(self, info, id):
        return MarketingCampaign.objects.prefetch_related("leads").get(pk=id)

    def resolve_leads(self, info, campaign_id=None, status=None):
        qs = Lead.objects.select_related("campaign").all()
        if campaign_id:
            qs = qs.filter(campaign_id=campaign_id)
        if status:
            qs = qs.filter(status=status)
        return qs

    def resolve_lead(self, info, id):
        return Lead.objects.select_related("campaign").get(pk=id)
