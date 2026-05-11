from graphql import GraphQLError
from functools import wraps
import base64

def get_db_id(global_id):
    """
    Helper para obtener el ID real de la DB desde un ID de Relay o un ID plano.
    """
    if not global_id:
        return None
    
    # Si ya es un número o string numérico directo
    if isinstance(global_id, int):
        return global_id
    if isinstance(global_id, str) and global_id.isdigit():
        return int(global_id)
    
    # Intentar decodificar Relay Global ID (Base64)
    try:
        # Añadir padding si falta (común en transmisiones base64)
        if isinstance(global_id, str):
            padding = len(global_id) % 4
            if padding:
                global_id += "=" * (4 - padding)
            
            decoded = base64.b64decode(global_id.encode('utf-8')).decode('utf-8')
            if ':' in decoded:
                # El formato de Relay es "TypeName:InternalID"
                return int(decoded.split(':')[1])
    except Exception:
        pass
        
    return None

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

def module_permission_required(module_name, action='view'):
    """
    Decorador para verificar si el usuario tiene un permiso específico sobre un módulo.
    Acciones válidas: 'view', 'add', 'change', 'delete'
    """
    def decorator(func):
        @wraps(func)
        def wrapper(root, info, *args, **kwargs):
            user = info.context.user
            if not user.is_authenticated:
                raise GraphQLError("No autenticado.")
            
            if user.is_superuser or user.is_staff:
                return func(root, info, *args, **kwargs)

            from users.permissions_map import MODULE_MODEL_MAP
            
            if module_name not in MODULE_MODEL_MAP:
                raise GraphQLError(f"Módulo '{module_name}' no definido.")

            app_label, model_name = MODULE_MODEL_MAP[module_name]
            
            # Formato de permiso de Django: app_label.accion_modelname
            permission_codename = f"{app_label}.{action}_{model_name}"
            
            if user.has_perm(permission_codename):
                return func(root, info, *args, **kwargs)
            
            raise GraphQLError(f"No tienes permiso para realizar la acción '{action}' en el módulo {module_name}.")
        return wrapper
    return decorator
