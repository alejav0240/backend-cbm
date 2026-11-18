from django.contrib import admin

from .models import ProcessingArtifact, ProcessingRun


class ProcessingArtifactInline(admin.TabularInline):
    model = ProcessingArtifact
    extra = 0


@admin.register(ProcessingRun)
class ProcessingRunAdmin(admin.ModelAdmin):
    list_display = ("external_run_id", "session", "status", "pipeline_version", "requested_at")
    list_filter = ("status", "pipeline_version")
    search_fields = ("external_run_id", "session__patient__first_name", "session__patient__last_name")
    inlines = [ProcessingArtifactInline]
