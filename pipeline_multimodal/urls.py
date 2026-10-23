from django.urls import path

from .views import analizar_video, obtener_resultado

urlpatterns = [
    path("analizar-video/", analizar_video, name="pipeline-multimodal-analizar-video"),
    path("resultados/<str:session_id>/", obtener_resultado, name="pipeline-multimodal-resultado"),
]
