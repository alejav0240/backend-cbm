from graphql_jwt.middleware import allow_any


def allow_refresh_token(info, **kwargs):
    path = info.path.as_list()
    return bool(path and path[0] == "refreshToken") or allow_any(info, **kwargs)
