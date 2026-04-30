from django.contrib.admin.apps import AdminConfig

class CBMAdminConfig(AdminConfig):
    default_site = "config.sites.CBMAdminSite"
