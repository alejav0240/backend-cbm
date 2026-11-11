from django.dispatch import receiver

from graphql_jwt.refresh_token.signals import refresh_token_rotated


@receiver(refresh_token_rotated)
def revoke_rotated_refresh_token(sender, request, refresh_token, **kwargs):
    """Make refresh-token rotation one-time-use even if the client retries."""
    refresh_token.revoke(request)
