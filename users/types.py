# users/types.py
from graphene_django import DjangoObjectType
from users.models import User, Notification

class UserType(DjangoObjectType):
    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "ci",
            "celular",
            "status",
            "visibility",
            "foto",
            "cv",
            "is_active",
            "date_joined",
        )

    def resolve_full_name(self, info):
        return f"{self.first_name} {self.last_name}".strip()

class NotificationType(DjangoObjectType):
    class Meta:
        model = Notification
        fields = ("id", "user", "message", "is_read", "created_at")
