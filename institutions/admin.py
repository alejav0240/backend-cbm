from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Institution, InstitutionGroup


class InstitutionGroupInline(TabularInline):
    model = InstitutionGroup
    extra = 1
    fields = ("name",)
    show_change_link = True


@admin.register(Institution)
class InstitutionAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = ("name","address", "contact_email", "contact_name", "contact_phone", "group_count")
    search_fields = ("name", "contact_name", "contact_email", "contact_phone")
    ordering = ("name",)
    inlines = (InstitutionGroupInline,)

    fieldsets = (
        (
            "Institución",
            {"fields": ("name", "contact_email", "contact_phone","address","contact_name")},
        ),
    )

    def group_count(self, obj):
        return obj.groups.count()

    group_count.short_description = "Grupos"


@admin.register(InstitutionGroup)
class InstitutionGroupAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = ("name", "institution","description")
    list_filter = ("institution",)
    search_fields = ("name", "institution__name")
    ordering = ("institution__name", "name")
    autocomplete_fields = ("institution",)

    fieldsets = (
        (
            "Grupo",
            {"fields": ("institution", "name","description")},
        ),
    )