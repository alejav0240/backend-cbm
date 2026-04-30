from unfold.sites import UnfoldAdminSite
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

class CBMAdminSite(UnfoldAdminSite):
    site_header = "CBM Plataforma"
    site_title = "CBM Admin"
    index_title = "Panel de Control"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Forzar la configuración del dashboard si no se toma de settings
        if not hasattr(self, "dashboard"):
             pass # Unfold suele tomarlo de settings si está bien configurado

cbm_admin_site = CBMAdminSite()
