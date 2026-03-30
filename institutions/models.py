from django.db import models


class Institution(models.Model):
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True, null=True)
    contact_name = models.CharField(max_length=255)
    contact_email = models.EmailField(blank=True, null=True)
    contact_phone = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        db_table = "institutions"

    def __str__(self):
        return self.name


class InstitutionGroup(models.Model):
    institution = models.ForeignKey(
        Institution, on_delete=models.CASCADE, related_name="groups"
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "institution_groups"

    def __str__(self):
        return f"{self.name} — {self.institution}"