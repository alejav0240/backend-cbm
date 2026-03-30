from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ci = models.CharField(max_length=50, unique=True)
    celular = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, default="active")
    visibility = models.CharField(max_length=20, default="public")
    foto = models.CharField(max_length=100, blank=True)
    cv = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "users"

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.username})"


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notificación para {self.user} — {'leída' if self.is_read else 'no leída'}"