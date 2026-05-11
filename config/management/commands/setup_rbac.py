from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from users.permissions_map import MODULE_MODEL_MAP

class Command(BaseCommand):
    help = 'Crea grupos por defecto y asigna todos los permisos según el mapa de módulos.'

    def handle(self, *args, **options):
        # 1. Crear grupo Administrador con TODO
        admin_group, created = Group.objects.get_or_create(name='Administrador')
        all_perms = Permission.objects.all()
        admin_group.permissions.set(all_perms)
        self.stdout.write(self.style.SUCCESS('Grupo Administrador configurado con todos los permisos.'))

        # 2. Crear grupo Terapeuta con permisos clínicos
        terapeuta_group, created = Group.objects.get_or_create(name='Terapeuta')
        clinical_modules = ['pacientes', 'sesiones', 'agenda', 'evaluaciones', 'planes', 'escalas', 'informes', 'recursos']
        
        terapeuta_perms = []
        for mod in clinical_modules:
            app_label, model_name = MODULE_MODEL_MAP[mod]
            perms = Permission.objects.filter(content_type__app_label=app_label, content_type__model=model_name)
            terapeuta_perms.extend(list(perms))
        
        terapeuta_group.permissions.set(terapeuta_perms)
        self.stdout.write(self.style.SUCCESS(f'Grupo Terapeuta configurado con módulos: {", ".join(clinical_modules)}'))

        # 3. Crear grupo Recepción con permisos administrativos
        recepcion_group, created = Group.objects.get_or_create(name='Recepcion')
        admin_modules = ['pacientes', 'sesiones', 'agenda', 'pagos', 'gastos', 'instituciones']
        
        recepcion_perms = []
        for mod in admin_modules:
            app_label, model_name = MODULE_MODEL_MAP[mod]
            # Recepción suele tener solo view y add
            perms = Permission.objects.filter(
                content_type__app_label=app_label, 
                content_type__model=model_name,
                codename__regex=r'^(view|add)_'
            )
            recepcion_perms.extend(list(perms))
            
        recepcion_group.permissions.set(recepcion_perms)
        self.stdout.write(self.style.SUCCESS(f'Grupo Recepción configurado con módulos (view/add): {", ".join(admin_modules)}'))

        self.stdout.write(self.style.SUCCESS('¡Configuración de RBAC completada exitosamente!'))
