import graphene
from graphql import GraphQLError

from marketing.models import MarketingCampaign, Lead, BlogPost
from marketing.type import MarketingCampaignType, LeadType, BlogPostType
from config.utils import module_permission_required, get_db_id


class Query(graphene.ObjectType):
    blog_posts = graphene.List(BlogPostType, status=graphene.String())
    blog_post = graphene.Field(BlogPostType, id=graphene.ID(required=True))

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

    @module_permission_required('blog', action='view')
    def resolve_blog_posts(self, info, status=None):
        qs = BlogPost.objects.all()
        if status:
            qs = qs.filter(status=status)
        return qs

    @module_permission_required('blog', action='view')
    def resolve_blog_post(self, info, id):
        real_id = get_db_id(id)
        try:
            return BlogPost.objects.get(pk=real_id)
        except BlogPost.DoesNotExist:
            raise GraphQLError("Artículo no encontrado")

    @module_permission_required('marketing', action='view')
    def resolve_marketing_campaigns(self, info, status=None, platform=None):
        qs = MarketingCampaign.objects.prefetch_related("leads").all()
        if status:
            qs = qs.filter(status=status)
        if platform:
            qs = qs.filter(platform__icontains=platform)
        return qs

    @module_permission_required('marketing', action='view')
    def resolve_marketing_campaign(self, info, id):
        real_id = get_db_id(id)
        try:
            return MarketingCampaign.objects.prefetch_related("leads").get(pk=real_id)
        except MarketingCampaign.DoesNotExist:
            raise GraphQLError("Campaña no encontrada")

    @module_permission_required('marketing', action='view')
    def resolve_leads(self, info, campaign_id=None, status=None):
        qs = Lead.objects.select_related("campaign").all()
        if campaign_id:
            real_campaign_id = get_db_id(campaign_id)
            qs = qs.filter(campaign_id=real_campaign_id)
        if status:
            qs = qs.filter(status=status)
        return qs

    @module_permission_required('marketing', action='view')
    def resolve_lead(self, info, id):
        real_id = get_db_id(id)
        try:
            return Lead.objects.select_related("campaign").get(pk=real_id)
        except Lead.DoesNotExist:
            raise GraphQLError("Lead no encontrado")
