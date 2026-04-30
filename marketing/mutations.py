import graphene
from decimal import Decimal
from graphql import GraphQLError
from marketing.models import MarketingCampaign, Lead, BlogPost
from marketing.type import MarketingCampaignType, LeadType, BlogPostType

class CreateBlogPost(graphene.Mutation):
    class Arguments:
        title = graphene.String(required=True)
        excerpt = graphene.String()
        content = graphene.String(required=True)
        category = graphene.String(required=True)
        author = graphene.String(required=True)
        image_url = graphene.String()
        read_time = graphene.String()
        status = graphene.String()

    post = graphene.Field(BlogPostType)

    def mutate(self, info, title, content, category, author, excerpt=None, image_url=None, read_time=None, status="draft"):
        post = BlogPost.objects.create(
            title=title,
            excerpt=excerpt,
            content=content,
            category=category,
            author=author,
            image_url=image_url,
            read_time=read_time,
            status=status
        )
        return CreateBlogPost(post=post)

class UpdateBlogPost(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        title = graphene.String()
        excerpt = graphene.String()
        content = graphene.String()
        category = graphene.String()
        author = graphene.String()
        image_url = graphene.String()
        read_time = graphene.String()
        status = graphene.String()

    post = graphene.Field(BlogPostType)

    def mutate(self, info, id, **kwargs):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
            
        try:
            post = BlogPost.objects.get(pk=real_id)
            for key, value in kwargs.items():
                setattr(post, key, value)
            post.save()
            return UpdateBlogPost(post=post)
        except BlogPost.DoesNotExist:
            raise GraphQLError("Artículo no encontrado")

class DeleteBlogPost(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    success = graphene.Boolean()

    def mutate(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
            
        try:
            post = BlogPost.objects.get(pk=real_id)
            post.delete()
            return DeleteBlogPost(success=True)
        except BlogPost.DoesNotExist:
            return DeleteBlogPost(success=False)

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

class UpdateCampaign(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        name = graphene.String()
        platform = graphene.String()
        budget = graphene.Float()
        status = graphene.String()

    campaign = graphene.Field(MarketingCampaignType)

    def mutate(self, info, id, **kwargs):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        
        try:
            campaign = MarketingCampaign.objects.get(pk=real_id)
            for key, value in kwargs.items():
                if key == 'budget':
                    setattr(campaign, key, Decimal(str(value)))
                else:
                    setattr(campaign, key, value)
            campaign.save()
            return UpdateCampaign(campaign=campaign)
        except MarketingCampaign.DoesNotExist:
            raise GraphQLError("Campaña no encontrada")

class DeleteCampaign(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    success = graphene.Boolean()

    def mutate(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        try:
            campaign = MarketingCampaign.objects.get(pk=real_id)
            campaign.delete()
            return DeleteCampaign(success=True)
        except MarketingCampaign.DoesNotExist:
            return DeleteCampaign(success=False)

class DeleteLead(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    success = graphene.Boolean()

    def mutate(self, info, id):
        try:
            real_id = int(graphene.relay.Node.from_global_id(id)[1])
        except:
            real_id = id
        try:
            lead = Lead.objects.get(pk=real_id)
            lead.delete()
            return DeleteLead(success=True)
        except Lead.DoesNotExist:
            return DeleteLead(success=False)

class Mutation(graphene.ObjectType):
    create_campaign = CreateCampaign.Field()
    update_campaign = UpdateCampaign.Field()
    delete_campaign = DeleteCampaign.Field()
    update_campaign_spent = UpdateCampaignSpent.Field()
    create_lead = CreateLead.Field()
    update_lead_status = UpdateLeadStatus.Field()
    delete_lead = DeleteLead.Field()
    create_blog_post = CreateBlogPost.Field()
    update_blog_post = UpdateBlogPost.Field()
    delete_blog_post = DeleteBlogPost.Field()
