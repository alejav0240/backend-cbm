from django.urls import path

from .views import analizar_video


urlpatterns = [
    path("analizar-video/", analizar_video, name="analizar-video"),
]
