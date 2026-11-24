from graphql_jwt.exceptions import JSONWebTokenError
from graphql_jwt.refresh_token.shortcuts import get_refresh_token
from graphql_jwt.refresh_token.utils import get_refresh_token_model
from graphql_jwt.settings import jwt_settings


def revoke_user_refresh_tokens(user):
    """Revoke every active long-running refresh token owned by a user."""
    refresh_token_model = get_refresh_token_model()
    for refresh_token in refresh_token_model.objects.filter(
        user=user,
        revoked__isnull=True,
    ):
        refresh_token.revoke()


def revoke_cookie_refresh_token(request):
    """Revoke the refresh token from the HttpOnly cookie, if it is valid."""
    token = request.COOKIES.get(jwt_settings.JWT_REFRESH_TOKEN_COOKIE_NAME)
    if not token:
        return

    try:
        get_refresh_token(token, request).revoke()
    except JSONWebTokenError:
        # Logout is idempotent: an expired or already-revoked token is harmless.
        return
