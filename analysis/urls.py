from django.urls import path

from .views import processing_callback

urlpatterns = [
    path("processing-callback/", processing_callback, name="processing-callback"),
]
