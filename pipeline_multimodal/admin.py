from django.contrib import admin

from .models import TherapistDataset, TherapistDatasetSample


class TherapistDatasetSampleInline(admin.TabularInline):
    model = TherapistDatasetSample
    extra = 0


@admin.register(TherapistDataset)
class TherapistDatasetAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "status", "created_at", "updated_at")
    list_filter = ("status",)
    search_fields = ("name", "owner__username", "owner__email")
    inlines = (TherapistDatasetSampleInline,)


@admin.register(TherapistDatasetSample)
class TherapistDatasetSampleAdmin(admin.ModelAdmin):
    list_display = ("dataset", "session_id", "window_id", "reviewed", "updated_at")
    list_filter = ("reviewed",)
    search_fields = ("session_id", "window_id", "dataset__name")
