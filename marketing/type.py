import graphene
from graphene_django import DjangoObjectType

from .models import MarketingCampaign, Lead, BlogPost


class BlogPostType(DjangoObjectType):
    class Meta:
        model = BlogPost
        fields = (
            "id", "title", "excerpt", "content", "category",
            "author", "image_url", "read_time", "status",
            "created_at", "updated_at"
        )


class MarketingCampaignType(DjangoObjectType):
    remaining_budget = graphene.Float()

    class Meta:
        model = MarketingCampaign
        fields = (
            "id", "name", "platform", "status",
            "budget", "spent",
            "created_at", "updated_at",
            "leads",
        )

    def resolve_remaining_budget(self, info):
        return float(self.remaining_budget)


class LeadType(DjangoObjectType):
    class Meta:
        model = Lead
        fields = (
            "id", "name", "phone", "email",
            "status", "campaign",
            "created_at", "updated_at",
        )


# ── Tipos paginados ────────────────────────────────────────────────────────────

class PaginatedBlogPosts(graphene.ObjectType):
    results = graphene.List(BlogPostType)
    total_count = graphene.Int()
    total_pages = graphene.Int()
    current_page = graphene.Int()


class PaginatedCampaigns(graphene.ObjectType):
    results = graphene.List(MarketingCampaignType)
    total_count = graphene.Int()
    total_pages = graphene.Int()
    current_page = graphene.Int()


class PaginatedLeads(graphene.ObjectType):
    results = graphene.List(LeadType)
    total_count = graphene.Int()
    total_pages = graphene.Int()
    current_page = graphene.Int()
