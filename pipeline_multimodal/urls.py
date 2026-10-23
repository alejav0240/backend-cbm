from django.urls import path

from .views import analizar_video, obtener_resultado, crear_trabajo, obtener_trabajo

urlpatterns = [
    path("analizar-video/", analizar_video, name="pipeline-multimodal-analizar-video"),
    path("resultados/<str:session_id>/", obtener_resultado, name="pipeline-multimodal-resultado"),
    path("trabajos/", crear_trabajo, name="pipeline-multimodal-crear-trabajo"),
    path("trabajos/<uuid:job_id>/", obtener_trabajo, name="pipeline-multimodal-obtener-trabajo"),
]
