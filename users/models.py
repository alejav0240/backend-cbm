from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    name = models.CharField(max_length=150)
    carnet = models.CharField(max_length=50, unique=True)
    type = models.CharField(max_length=50)  # admin, estudiante, etc
    phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, default="active")
    visibility = models.CharField(max_length=20, default="public")

    def __str__(self):
        return self.username