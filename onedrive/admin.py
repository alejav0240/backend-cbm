from django.contrib import admin
from unfold.admin import ModelAdmin

from onedrive.models import OneDriveConnection


@admin.register(OneDriveConnection)
class OneDriveConnectionAdmin(ModelAdmin):
    list_display = ("user_email", "is_active", "created_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("user_email",)
    readonly_fields = ("refresh_token_encrypted", "created_at", "updated_at")
    actions = ["desconectar"]

    fieldsets = (
        (
            "Conexión",
            {"fields": ("user_email", "is_active", "refresh_token_encrypted")},
        ),
        ("Auditoría", {"fields": ("created_at", "updated_at")}),
    )

    @admin.action(description="Desconectar OneDrive")
    def desconectar(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, "Conexión OneDrive desactivada.")
