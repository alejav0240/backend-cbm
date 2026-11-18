from django.contrib import admin

from .annotation_models import Adjudication, AnnotationCase, AnnotationReview, ParticipantAnchor
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


@admin.register(AnnotationCase)
class AnnotationCaseAdmin(admin.ModelAdmin):
    list_display = ("window_id", "label", "modality", "status", "run", "start_seconds", "end_seconds")
    list_filter = ("status", "modality", "source")
    search_fields = ("window_id", "label", "run__external_run_id")
    inlines = []


@admin.register(AnnotationReview)
class AnnotationReviewAdmin(admin.ModelAdmin):
    list_display = ("case", "reviewer", "decision", "reviewed_at")
    list_filter = ("decision",)


@admin.register(ParticipantAnchor)
class ParticipantAnchorAdmin(admin.ModelAdmin):
    list_display = ("run", "track_id", "role", "reviewed_by", "reviewed_at")
    list_filter = ("role",)


@admin.register(Adjudication)
class AdjudicationAdmin(admin.ModelAdmin):
    list_display = ("case", "adjudicator", "final_decision", "adjudicated_at")
