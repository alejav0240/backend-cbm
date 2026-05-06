from graphql import GraphQLError
from functools import wraps

def login_required(func):
    @wraps(func)
    def wrapper(root, info, *args, **kwargs):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("No autenticado.")
        return func(root, info, *args, **kwargs)
    return wrapper

def staff_member_required(func):
    @wraps(func)
    def wrapper(root, info, *args, **kwargs):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("No autenticado.")
        if not user.is_staff:
            raise GraphQLError("No autorizado: se requiere rol de administrador.")
        return func(root, info, *args, **kwargs)
    return wrapper
