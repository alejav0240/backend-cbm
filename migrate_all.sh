#!/usr/bin/env bash
# =============================================================================
# migrate_all.sh — Pipeline completo de migración CBM Platform
#
# Pasos:
#   1. Aplica migraciones Django
#   2. Crea/actualiza superusuario admin
#   3. Recarga el backup SQL en el contenedor legacy (MariaDB)
#   4. Ejecuta el ETL legacy → Django (importar_laravel)
#   5. Exporta un backup de PostgreSQL con timestamp
#
# Uso:
#   ./migrate_all.sh [opciones]
#
# Opciones:
#   --skip-legacy-reload   Omite el drop/create + carga del legacy.sql
#   --dry-run              Pasa --dry-run al ETL (no persiste datos)
#   --no-backup            Omite el export final de PostgreSQL
#   -h, --help             Muestra esta ayuda
# =============================================================================

set -euo pipefail

# ── Colores ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

log()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
ok()     { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()   { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()  { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
header() { echo -e "\n${BOLD}${CYAN}══ $* ══${RESET}"; }

# ── Configuración ─────────────────────────────────────────────────────────────
DJANGO_CONTAINER="django_backend"
LEGACY_CONTAINER="legacy_mariadb"
PG_CONTAINER="postgres_db"

# Ruta al archivo SQL legacy (relativa al directorio donde se ejecuta el script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEGACY_SQL="${SCRIPT_DIR}/../legacy.sql"
BACKUP_DIR="${SCRIPT_DIR}/.."

LEGACY_DB="hmusicot_musicoterapiadb"
LEGACY_USER="hmusicot"
LEGACY_PASSWORD='GI8}(&Fg~5J;'
LEGACY_HOST="legacy_mariadb"
LEGACY_PORT="3306"

PG_USER="django_user"
PG_DB="django_db"

ADMIN_USERNAME="admin"
ADMIN_EMAIL="admin@admin.com"
ADMIN_PASSWORD="admin"

# ── Flags ─────────────────────────────────────────────────────────────────────
SKIP_LEGACY_RELOAD=false
DRY_RUN=false
NO_BACKUP=false

# ── Parseo de argumentos ──────────────────────────────────────────────────────
for arg in "$@"; do
  case $arg in
    --skip-legacy-reload) SKIP_LEGACY_RELOAD=true ;;
    --dry-run)            DRY_RUN=true ;;
    --no-backup)          NO_BACKUP=true ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \?//' | sed -n '/^Uso:/,/^===/p' | head -n -1
      exit 0
      ;;
    *) warn "Argumento desconocido: $arg (ignorado)" ;;
  esac
done

# ── Verificación de contenedores ──────────────────────────────────────────────
header "Verificando contenedores"

for container in "$DJANGO_CONTAINER" "$LEGACY_CONTAINER" "$PG_CONTAINER"; do
  if ! docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
    error "El contenedor '$container' no está corriendo."
    error "Levanta los servicios con: docker compose up -d"
    exit 1
  fi
  ok "$container — corriendo"
done

# ── Paso 1: Migraciones Django ────────────────────────────────────────────────
header "Paso 1 — Migraciones Django"
docker exec "$DJANGO_CONTAINER" python manage.py migrate
ok "Migraciones aplicadas"

# ── Paso 2: Superusuario ──────────────────────────────────────────────────────
header "Paso 2 — Superusuario ($ADMIN_USERNAME)"
docker exec "$DJANGO_CONTAINER" python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='${ADMIN_USERNAME}').exists():
    User.objects.create_superuser('${ADMIN_USERNAME}', '${ADMIN_EMAIL}', '${ADMIN_PASSWORD}')
    print('Superusuario CREADO')
else:
    u = User.objects.get(username='${ADMIN_USERNAME}')
    u.set_password('${ADMIN_PASSWORD}')
    u.email = '${ADMIN_EMAIL}'
    u.is_superuser = True
    u.is_staff = True
    u.save()
    print('Superusuario ACTUALIZADO')
"
ok "Superusuario listo — ${ADMIN_USERNAME} / ${ADMIN_PASSWORD}"

# ── Paso 3: Recargar legacy SQL ───────────────────────────────────────────────
if [ "$SKIP_LEGACY_RELOAD" = false ]; then
  header "Paso 3 — Recargar BD Legacy (MariaDB)"

  if [ ! -f "$LEGACY_SQL" ]; then
    error "No se encontró el archivo: $LEGACY_SQL"
    error "Coloca legacy.sql en: $(dirname "$LEGACY_SQL")"
    exit 1
  fi

  log "Dropeando y recreando base de datos legacy..."
  docker exec "$LEGACY_CONTAINER" mysql \
    -u"$LEGACY_USER" -p"$LEGACY_PASSWORD" \
    -e "DROP DATABASE IF EXISTS ${LEGACY_DB}; CREATE DATABASE ${LEGACY_DB};"

  log "Importando $(basename "$LEGACY_SQL")..."
  docker exec -i "$LEGACY_CONTAINER" mysql \
    -u"$LEGACY_USER" -p"$LEGACY_PASSWORD" \
    "$LEGACY_DB" < "$LEGACY_SQL"

  TABLES=$(docker exec "$LEGACY_CONTAINER" mysql \
    -u"$LEGACY_USER" -p"$LEGACY_PASSWORD" \
    -D "$LEGACY_DB" -e "SHOW TABLES;" 2>/dev/null | tail -n +2 | wc -l)
  ok "BD legacy cargada — $TABLES tablas"
else
  warn "Paso 3 omitido (--skip-legacy-reload)"
fi

# ── Paso 4: ETL importar_laravel ──────────────────────────────────────────────
header "Paso 4 — ETL Legacy → Django"

if [ "$DRY_RUN" = true ]; then
  warn "Modo DRY-RUN activado — no se persistirán datos"
  ETL_MODE="--dry-run"
else
  ETL_MODE="--truncate"
fi

docker exec "$DJANGO_CONTAINER" python manage.py importar_laravel \
  --host   "$LEGACY_HOST" \
  --user   "$LEGACY_USER" \
  --password "$LEGACY_PASSWORD" \
  --database "$LEGACY_DB" \
  --port   "$LEGACY_PORT" \
  $ETL_MODE

ok "ETL completado"

# ── Paso 5: Backup PostgreSQL ─────────────────────────────────────────────────
if [ "$NO_BACKUP" = false ]; then
  header "Paso 5 — Exportar backup PostgreSQL"

  BACKUP_FILE="$(realpath "$BACKUP_DIR")/backup_$(date +%Y%m%d_%H%M%S).sql"
  docker exec "$PG_CONTAINER" pg_dump -U "$PG_USER" -d "$PG_DB" > "$BACKUP_FILE"
  SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
  ok "Backup guardado: $BACKUP_FILE ($SIZE)"
else
  warn "Paso 5 omitido (--no-backup)"
fi

# ── Resumen ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}════════════════════════════════════════${RESET}"
echo -e "${BOLD}${GREEN}  ✅  Pipeline completado exitosamente   ${RESET}"
echo -e "${BOLD}${GREEN}════════════════════════════════════════${RESET}"
echo ""
