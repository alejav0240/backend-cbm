from django.contrib.auth.models import Permission

# Mapeamos los módulos de la UI a los (app_label, model) nativos de Django
MODULE_MODEL_MAP = {
    'pacientes': ('clinical', 'patient'),
    'sesiones': ('therapeutic_sessions', 'session'),
    'agenda': ('clinical', 'patientclinicalnote'), # Usado como proxy para agenda
    'pagos': ('finance', 'payment'),
    'recursos': ('therapeutic_sessions', 'digitalresource'),
    'formularios': ('evaluations', 'form'),
    'roles': ('auth', 'group'),
    'configuracion': ('users', 'user'),
}

def get_permissions_for_modules(modules):
    """Convierte una lista de strings de módulos ['pacientes'] a objetos Permission de Django."""
    perms = []
    for mod in modules:
        if mod in MODULE_MODEL_MAP:
            app_label, model_name = MODULE_MODEL_MAP[mod]
            # Obtenemos todos los permisos CRUD (add, change, delete, view) para este modelo
            model_perms = Permission.objects.filter(content_type__app_label=app_label, content_type__model=model_name)
            perms.extend(list(model_perms))
    return perms

def get_modules_for_group(group):
    """Convierte los permisos de un auth.Group a una lista de strings de módulos para la UI."""
    modules = []
    group_perms = group.permissions.select_related('content_type').all()
    # Creamos un set de los modelos a los que tiene acceso este grupo
    group_models = set((p.content_type.app_label, p.content_type.model) for p in group_perms)
    
    for mod, (app_label, model_name) in MODULE_MODEL_MAP.items():
        if (app_label, model_name) in group_models:
            modules.append(mod)
    return modules
