import graphene
from graphql import GraphQLError

from marketing.models import MarketingCampaign, Lead, BlogPost
from marketing.type import MarketingCampaignType, LeadType, BlogPostType, PaginatedBlogPosts, PaginatedCampaigns, PaginatedLeads
from config.utils import module_permission_required, get_db_id


class Query(graphene.ObjectType):
    blog_posts = graphene.Field(
        PaginatedBlogPosts,
        status=graphene.String(),
        search=graphene.String(),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
    )
    blog_post = graphene.Field(BlogPostType, id=graphene.ID(required=True))

    marketing_campaigns = graphene.Field(
        PaginatedCampaigns,
        status=graphene.String(),
        platform=graphene.String(),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
    )
    marketing_campaign = graphene.Field(MarketingCampaignType, id=graphene.ID(required=True))

    leads = graphene.Field(
        PaginatedLeads,
        campaign_id=graphene.ID(),
        status=graphene.String(),
        search=graphene.String(),
        page=graphene.Int(default_value=1),
        page_size=graphene.Int(default_value=10),
    )
    lead = graphene.Field(LeadType, id=graphene.ID(required=True))

    @module_permission_required('blog', action='view')
    def resolve_blog_posts(self, info, status=None, search=None, page=1, page_size=10):
        qs = BlogPost.objects.all()
        if status:
            qs = qs.filter(status=status)
        if search:
            qs = qs.filter(title__icontains=search)
        total_count = qs.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        offset = (page - 1) * page_size
        return PaginatedBlogPosts(
            results=qs[offset:offset + page_size],
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )

    @module_permission_required('blog', action='view')
    def resolve_blog_post(self, info, id):
        real_id = get_db_id(id)
        try:
            return BlogPost.objects.get(pk=real_id)
        except BlogPost.DoesNotExist:
            raise GraphQLError("Artículo no encontrado")

    @module_permission_required('marketing', action='view')
    def resolve_marketing_campaigns(self, info, status=None, platform=None, page=1, page_size=10):
        qs = MarketingCampaign.objects.prefetch_related("leads").all()
        if status:
            qs = qs.filter(status=status)
        if platform:
            qs = qs.filter(platform__icontains=platform)
        total_count = qs.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        offset = (page - 1) * page_size
        return PaginatedCampaigns(
            results=qs[offset:offset + page_size],
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )

    @module_permission_required('marketing', action='view')
    def resolve_marketing_campaign(self, info, id):
        real_id = get_db_id(id)
        try:
            return MarketingCampaign.objects.prefetch_related("leads").get(pk=real_id)
        except MarketingCampaign.DoesNotExist:
            raise GraphQLError("Campaña no encontrada")

    @module_permission_required('marketing', action='view')
    def resolve_leads(self, info, campaign_id=None, status=None, search=None, page=1, page_size=10):
        qs = Lead.objects.select_related("campaign").all()
        if campaign_id:
            qs = qs.filter(campaign_id=get_db_id(campaign_id))
        if status:
            qs = qs.filter(status=status)
        if search:
            qs = qs.filter(name__icontains=search)
        total_count = qs.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        offset = (page - 1) * page_size
        return PaginatedLeads(
            results=qs[offset:offset + page_size],
            total_count=total_count,
            total_pages=total_pages,
            current_page=page,
        )

    @module_permission_required('marketing', action='view')
    def resolve_lead(self, info, id):
        real_id = get_db_id(id)
        try:
            return Lead.objects.select_related("campaign").get(pk=real_id)
        except Lead.DoesNotExist:
            raise GraphQLError("Lead no encontrado")
