from django.contrib.auth.models import Permission

# Mapeamos los módulos de la UI a los (app_label, model) nativos de Django
MODULE_MODEL_MAP = {
    'pacientes': ('clinical', 'patient'),
    'sesiones': ('therapeutic_sessions', 'session'),
    'agenda': ('clinical', 'patientclinicalnote'), # Proxy para agenda
    'pagos': ('finance', 'payment'),
    'recursos': ('therapeutic_sessions', 'digitalresource'),
    'formularios': ('evaluations', 'form'),
    'roles': ('auth', 'group'),
    'usuarios': ('users', 'user'),
    'evaluaciones': ('evaluations', 'evaluation'),
    'planes': ('clinical', 'interventionplan'),
    'escalas': ('evaluations', 'evaluationscale'),
    'informes': ('clinical', 'therapyreport'),
    'gastos': ('finance', 'expense'),
    'inventario': ('therapeutic_sessions', 'inventoryitem'),
    'analisis': ('clinical', 'therapyreport'), # Reutilizamos informes para análisis
    'marketing': ('marketing', 'marketingcampaign'),
    'blog': ('marketing', 'blogpost'),
    'cursos': ('finance', 'course'),
    'instituciones': ('institutions', 'institution'),
    'ajustes': ('users', 'user'),
}

def get_permissions_for_modules(modules):
    """Convierte módulos ['pacientes'] o permisos ['pacientes:view'] a objetos Permission de Django."""
    perms = []
    valid_actions = {'view', 'add', 'change', 'delete'}

    for raw_module in modules:
        mod, action = (raw_module.split(':', 1) + [None])[:2] if ':' in raw_module else (raw_module, None)

        if mod in MODULE_MODEL_MAP:
            app_label, model_name = MODULE_MODEL_MAP[mod]

            model_perms = Permission.objects.filter(
                content_type__app_label=app_label,
                content_type__model=model_name
            )

            if action in valid_actions:
                model_perms = model_perms.filter(codename=f'{action}_{model_name}')

            perms.extend(list(model_perms))
    return perms

def get_modules_for_group(group):
    """Convierte los permisos de un auth.Group a permisos por acción para la UI."""
    modules = []
    group_perms = group.permissions.select_related('content_type').all()
    group_permissions = set(
        (p.content_type.app_label, p.content_type.model, p.codename)
        for p in group_perms
    )
    
    for mod, (app_label, model_name) in MODULE_MODEL_MAP.items():
        for action in ['view', 'add', 'change', 'delete']:
            if (app_label, model_name, f'{action}_{model_name}') in group_permissions:
                modules.append(f'{mod}:{action}')
    return modules
