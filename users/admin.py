# users/admin.py

from django.contrib import admin
from django.contrib.auth.models import Group
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin, GroupAdmin as BaseGroupAdmin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html

from unfold.admin import ModelAdmin, TabularInline
from unfold.forms import UserChangeForm, UserCreationForm
from unfold.decorators import display

from .models import Notification, User

admin.site.unregister(Group)


class UserInline(TabularInline):
    model = User.groups.through
    extra = 1
    verbose_name = "Usuario"
    verbose_name_plural = "Usuarios en este grupo"
    autocomplete_fields = ("user",)


@admin.register(Group)
class GroupAdmin(ModelAdmin, BaseGroupAdmin):
    compressed_fields = True
    list_fullwidth = True
    search_fields = ("name",)
    filter_horizontal = ("permissions",)
    inlines = (UserInline,)


# ==============================
# INLINE: NOTIFICATIONS
# ==============================
class NotificationInline(TabularInline):
    model = Notification
    extra = 0
    fields = ("message", "is_read", "created_at")
    readonly_fields = ("created_at",)
    show_change_link = False


# ==============================
# USER ADMIN
# ==============================
@admin.register(User)
class UserAdmin(ModelAdmin, BaseUserAdmin):
    change_list_template = "admin/custom_change_list.html"
    compressed_fields = True
    warn_unsaved_form = True
    list_fullwidth = True
    list_filter_submit = True

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        active_users = User.objects.filter(is_active=True).count()
        staff_users = User.objects.filter(is_staff=True).count()
        total_users = User.objects.count()

        extra_context["kpis"] = [
            {"label": "Total Usuarios", "value": total_users, "icon": "group", "color": "primary"},
            {"label": "Activos", "value": active_users, "icon": "person_check", "color": "success"},
            {"label": "Personal (Staff)", "value": staff_users, "icon": "shield_person", "color": "warning"},
            {"label": "Grupos", "value": Group.objects.count(), "icon": "admin_panel_settings", "color": "danger"},
        ]
        return super().changelist_view(request, extra_context=extra_context)

    form = UserChangeForm
    add_form = UserCreationForm

    # ==============================
    # ADD USER
    # ==============================
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "username",
                "password1",
                "password2",
                "first_name",
                "last_name",
                "ci",
                "celular",
                "email",
            ),
        }),
    )

    # ==============================
    # LIST VIEW
    # ==============================
    list_display = (
        "username",
        "full_name",
        "ci",
        "celular",
        "display_status",
        "is_staff",
        "is_active",
        "display_active",
        "email",
        "get_groups",
        "show_foto",
    )

    list_filter = ("status", "visibility", "groups", "is_staff")
    search_fields = ("username", "email", "first_name", "last_name", "ci")
    ordering = ("last_name", "first_name")
    inlines = (NotificationInline,)

    filter_horizontal = ("groups", "user_permissions")

    # ==============================
    # FIELDSETS
    # ==============================
    fieldsets = (
        (
            _("Datos personales"),
            {
                "fields": (
                    ("first_name", "last_name"),
                    ("ci", "celular"),
                    "foto",
                    "cv",
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
            "Roles y Permisos",
            {
                "fields": (
                    "groups",
                    "is_superuser",
                ),
            }
        ),
        (
            "Estado",
            {
                "fields": (
                    "status",
                    "visibility",
                    "is_active",
                    "is_staff",
                )
            },
        ),
    )

    # ==============================
    # OPTIMIZACIÓN QUERY
    # ==============================
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("groups")

    # ==============================
    # MÉTODOS CUSTOM
    # ==============================
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

    @display(
        description="Estado",
        label={
            "active": "success",
            "inactive": "danger",
            "blocked": "warning",
        },
    )
    def display_status(self, obj):
        return obj.status

    @display(description="Roles")
    def get_groups(self, obj):
        return ", ".join([g.name for g in obj.groups.all()]) if obj.groups.exists() else "Sin Rol"

    @display(description="Foto")
    def show_foto(self, obj):
        if obj.foto:
            try:
                return format_html(
                    '<img src="{}" width="40" height="40" style="border-radius:50%;" />',
                    obj.foto.url,
                )
            except:
                return "Sin imagen"
        return "Sin foto"


# ==============================
# NOTIFICATION ADMIN
# ==============================
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

    # ==============================
    # MÉTODOS
    # ==============================
    @display(description="Mensaje")
    def message_preview(self, obj):
        return obj.message[:80] + "..." if len(obj.message) > 80 else obj.message

    @display(
        description="Estado",
        label={True: "success", False: "warning"},
    )
    def display_read(self, obj):
        return "Leída" if obj.is_read else "No leída"

    # ==============================
    # ACTIONS
    # ==============================
    actions = ("mark_as_read", "mark_as_unread")

    @admin.action(description="Marcar como leídas")
    def mark_as_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        self.message_user(request, f"{updated} notificaciones marcadas como leídas")

    @admin.action(description="Marcar como no leídas")
    def mark_as_unread(self, request, queryset):
        updated = queryset.update(is_read=False)
        self.message_user(request, f"{updated} notificaciones marcadas como no leídas")