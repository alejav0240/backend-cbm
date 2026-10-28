from django.urls import path

from .views import (
    analizar_video,
    actualizar_demuca,
    obtener_resultado,
    crear_trabajo,
    obtener_trabajo,
)

urlpatterns = [
    path("analizar-video/", analizar_video, name="pipeline-multimodal-analizar-video"),
    path("resultados/<str:session_id>/", obtener_resultado, name="pipeline-multimodal-resultado"),
    path("resultados/<str:session_id>/demuca/", actualizar_demuca, name="pipeline-multimodal-actualizar-demuca"),
    path("trabajos/", crear_trabajo, name="pipeline-multimodal-crear-trabajo"),
    path("trabajos/<uuid:job_id>/", obtener_trabajo, name="pipeline-multimodal-obtener-trabajo"),
]
