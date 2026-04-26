from django.db import models


class MarketingCampaign(models.Model):

    class CampaignStatus(models.TextChoices):
        DRAFT = "draft", "Borrador"
        ACTIVE = "active", "Activa"
        PAUSED = "paused", "Pausada"
        FINISHED = "finished", "Finalizada"

    name = models.CharField(max_length=255)
    platform = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20, choices=CampaignStatus.choices, default=CampaignStatus.DRAFT
    )
    budget = models.DecimalField(max_digits=12, decimal_places=2)
    spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "marketing_campaigns"
        ordering = ["-created_at"]

    @property
    def remaining_budget(self):
        return self.budget - self.spent

    def __str__(self):
        return f"{self.name} ({self.platform}) — {self.get_status_display()}"


class Lead(models.Model):

    class LeadStatus(models.TextChoices):
        NEW = "new", "Nuevo"
        CONTACTED = "contacted", "Contactado"
        QUALIFIED = "qualified", "Calificado"
        LOST = "lost", "Perdido"

    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=LeadStatus.choices, default=LeadStatus.NEW)
    campaign = models.ForeignKey(
        MarketingCampaign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "leads"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} — {self.get_status_display()}"
