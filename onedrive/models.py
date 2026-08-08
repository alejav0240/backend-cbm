import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _get_fernet_key() -> bytes:
    key = getattr(settings, "ONEDRIVE_TOKEN_ENCRYPTION_KEY", None) or os.getenv(
        "ONEDRIVE_TOKEN_ENCRYPTION_KEY"
    )
    if key:
        return key.encode("utf-8")
    derived = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(derived)


def encrypt_token(token: str) -> str:
    return Fernet(_get_fernet_key()).encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(token_encrypted: str) -> str:
    try:
        return Fernet(_get_fernet_key()).decrypt(token_encrypted.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise ValueError("No se pudo descifrar el refresh token de OneDrive.")


class OneDriveConnection(models.Model):
    refresh_token_encrypted = models.TextField()
    user_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "onedrive_connections"
        verbose_name = "Conexión OneDrive"
        verbose_name_plural = "Conexiones OneDrive"

    def __str__(self):
        return f"OneDrive — {self.user_email or self.pk}"

    def save_refresh_token(self, token: str) -> None:
        self.refresh_token_encrypted = encrypt_token(token)
        self.save(
            update_fields=[
                "refresh_token_encrypted",
                "user_email",
                "is_active",
                "updated_at",
            ]
        )

    @classmethod
    def get_active(cls) -> "OneDriveConnection | None":
        return cls.objects.filter(is_active=True).first()

    @classmethod
    def decrypted_token(cls) -> str | None:
        connection = cls.get_active()
        if not connection or not connection.refresh_token_encrypted:
            return None
        try:
            return decrypt_token(connection.refresh_token_encrypted)
        except ValueError:
            return None
