# Guía de Desarrollo y Comandos

## Entorno de Desarrollo

El proyecto usa **Docker Compose** para levantar PostgreSQL, Django y Mailpit.
Ejecutá los comandos desde la raíz del workspace (`cbm-front`):

```bash
cp backend/.env.example backend/.env  # solo para ejecutar Django fuera de Docker; nunca lo subas
# Para Docker Compose, configurá el `.env` de la raíz con valores locales.

docker compose up -d db mailpit
# Para levantar toda la plataforma:
docker compose up -d
```

El backend queda disponible en `http://localhost:8000/graphql/` y PostgreSQL en el puerto `5432`.

### Comandos Frecuentes

Desde la raíz del workspace:

- **Migraciones:** `docker compose exec backend python manage.py migrate`
- **Crear migraciones:** `docker compose exec backend python manage.py makemigrations`
- **Crear superusuario:** `docker compose exec backend python manage.py createsuperuser`
- **Logs:** `docker compose logs -f backend db`

## Testing (Calidad de Código)

Cada nueva funcionalidad debe incluir pruebas en la app correspondiente. Las pruebas usan PostgreSQL; no dependen de SQLite.

### Ejecución reproducible

Con el servicio `db` iniciado:

```bash
docker compose run --rm backend python manage.py test --noinput --verbosity=1
```

Para ejecutar una aplicación específica:

```bash
docker compose run --rm backend python manage.py test users --noinput
```

También podés ejecutar las pruebas dentro de un backend ya iniciado:

```bash
docker compose exec backend python manage.py test --noinput --verbosity=1
```

Si ejecutás Django directamente fuera de Docker, PostgreSQL debe estar disponible en `DB_HOST`/`DB_PORT` y el entorno debe cargarse desde `backend/.env`.

## Estándares de Código

- **Tipado:** usar `Decimal` para valores financieros.
- **Transacciones:** usar `@transaction.atomic` en mutaciones que afecten múltiples tablas.
- **Casing:**
  - Modelos y DB: `snake_case`.
  - GraphQL arguments: `camelCase` (Graphene lo maneja automáticamente).
  - Clinical categories: `UPPERCASE` en base de datos.
