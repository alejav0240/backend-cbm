from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from unfold.admin import ModelAdmin, TabularInline
from unfold.admin import ModelAdmin
from unfold.forms import UserChangeForm, UserCreationForm
from unfold.decorators import display

from .models import Notification, User


class NotificationInline(TabularInline):
    model = Notification
    extra = 0
    fields = ("message", "is_read", "created_at")
    readonly_fields = ("created_at",)
    show_change_link = False

@admin.register(User)
class UserAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_fullwidth = True
    list_filter_submit = True

    form = UserChangeForm
    add_form = UserCreationForm

    list_display = (
        "username",
        "full_name",
        "ci",
        "celular",
        "status",
        "is_staff",
        "is_active",
        "email",
        "display_active",
        "get_groups"
    )
    list_filter = ("status", "visibility", "groups", "is_staff")
    search_fields = ("username", "email", "first_name", "last_name", "ci")
    ordering = ("last_name", "first_name")
    inlines = (NotificationInline,)

    fieldsets = (
        (
            _("Datos personales"),
            {
                "fields": (
                    ("first_name", "last_name"),
                    ("ci", "celular"),
                )
            },
        ),
        (
            "Acceso",
            {
                "fields": (
                    "username",
                    "email",
                    "password",
                )
            },
        ),
        (
            'Roles y Permisos',
            {
                'fields': (
                        'groups',
                        'is_superuser'
                ),
            }
        ),
        (
            "Estado",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                )
            },
        ),
    )

    filter_horizontal = ("groups", "user_permissions")

    @display(description=_("Usuario"), header=True)
    def display_header(self, instance):
        """Muestra el nombre con un estilo de encabezado en la lista"""
        return [
            f"{instance.first_name} {instance.last_name}",
            instance.username,
        ]


    @display(description="Nombre completo")
    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"

    @display(
        description="Activo",
        label={True: "success", False: "danger"},
        boolean=True,
    )
    def display_active(self, obj):
        return obj.is_active

    @display(description='Roles')
    def get_groups(self, obj):
        return ", ".join([g.name for g in obj.groups.all()]) if obj.groups.exists() else "Sin Rol"

@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    compressed_fields = True
    list_filter_submit = True

    list_display = ("user", "message_preview", "display_read", "created_at")
    list_filter = ("is_read",)
    search_fields = ("user__username", "user__email", "message")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    autocomplete_fields = ("user",)

    fieldsets = (
        (
            "Notificación",
            {"fields": ("user", "message", "is_read", "created_at")},
        ),
    )

    @display(description="Mensaje")
    def message_preview(self, obj):
        return obj.message[:80] + "..." if len(obj.message) > 80 else obj.message

    @display(
        description="Estado",
        label={True: "success", False: "warning"},
    )
    def display_read(self, obj):
        return "Leída" if obj.is_read else "No leída"

    actions = ("mark_as_read", "mark_as_unread")

    @admin.action(description="Marcar como leídas")
    def mark_as_read(self, request, queryset):
        queryset.update(is_read=True)

    @admin.action(description="Marcar como no leídas")
    def mark_as_unread(self, request, queryset):
        queryset.update(is_read=False)