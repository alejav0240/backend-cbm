from django.urls import path

from onedrive.views import onedrive_status, onedrive_token

urlpatterns = [
    path("token", onedrive_token, name="onedrive-token"),
    path("status", onedrive_status, name="onedrive-status"),
]
