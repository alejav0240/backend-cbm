# Guía de Desarrollo y Comandos

## Entorno de Desarrollo
El proyecto está containerizado con **Docker**. El servicio principal es `django_backend`.

### Comandos Frecuentes
- **Migraciones:** `docker exec django_backend python manage.py makemigrations`
- **Aplicar Migraciones:** `docker exec django_backend python manage.py migrate`
- **Crear Superuser:** `docker exec django_backend python manage.py createsuperuser`

## Testing (Calidad de Código)
Es mandatorio que cada nueva funcionalidad incluya sus tests en el archivo `tests.py` de la app correspondiente.

### Ejecución de Tests
- **Todos los tests:** `docker exec django_backend python manage.py test`
- **Por aplicación:** `docker exec django_backend python manage.py test <app_name>`

## Estándares de Código
- **Tipado:** Usar `Decimal` para valores financieros.
- **Transacciones:** Usar `@transaction.atomic` en mutaciones que afecten a múltiples tablas.
- **Casing:**
    - Modelos y DB: `snake_case`.
    - GraphQL Arguments: `camelCase` (Graphene lo maneja automáticamente).
    - Clinical Categories: `UPPERCASE` en base de datos.
