# ETL Migración Legacy Laravel → Django (importar_laravel.py)

Comando de migración completo que traslada datos desde una base de datos legacy Laravel (MariaDB) hacia modelos Django en PostgreSQL.

## 📋 Requisitos Previos

### Base de datos Legacy
- **Motor**: MariaDB/MySQL 5.7+
- **Acceso**: TCP directo o SSH tunnel disponible
- **Credenciales**: usuario con permisos SELECT en la DB legacy

### Entorno Django
- **Python**: 3.11+
- **Django**: 4.0+
- **Paquetes adicionales**:
  ```bash
  pip install mysql-connector-python sshtunnel
  ```

### Base de datos Destino
- **Motor**: PostgreSQL 12+
- **Migraciones**: Todas aplicadas (`python manage.py migrate`)

## 🚀 Configuración Inicial

### 1. Preparar la BD Legacy (si acceso remoto falla)

Si la conexión directa a la BD remota no funciona, crea un contenedor local:

```bash
docker run -d --name legacy_mariadb \
  --network cbm-platafom_cbm-network \
  -e MARIADB_ROOT_PASSWORD=legacy_root \
  -e MARIADB_DATABASE=hmusicot_musicoterapiadb \
  -e MARIADB_USER=hmusicot \
  -e MARIADB_PASSWORD='GI8}(&Fg~5J;' \
  mariadb:10.11
```

Restaura el backup SQL:

```bash
docker exec -i legacy_mariadb mysql -uhmusicot -p'GI8}(&Fg~5J;' \
  hmusicot_musicoterapiadb < lagacy.sql
```

### 2. Instalar Dependencias

Dentro del contenedor Django:

```bash
pip install mysql-connector-python sshtunnel
```

## 📖 Uso del Comando

### Sintaxis General

```bash
python manage.py importar_laravel [opciones]
```

### Opciones Disponibles

| Opción | Tipo | Default | Descripción |
|--------|------|---------|-------------|
| `--host` | string | cpanel.musicoterapiabolivia.com | Host de la BD legacy |
| `--user` | string | hmusicot | Usuario de la BD legacy |
| `--password` | string | (requerido) | Contraseña de la BD legacy |
| `--database` | string | hmusicot_musicoterapiadb | Nombre de la BD legacy |
| `--port` | int | 3306 | Puerto MySQL |
| `--dry-run` | flag | - | Ejecuta ETL sin persistir (test mode) |
| `--truncate` | flag | - | Limpia datos previos y recarga |

## 🔄 Flujo de Migración

El comando ejecuta el siguiente flujo:

```
1. Conexión a BD legacy
2. Lectura de tablas legacy
3. Truncado (opcional) de datos migrados previos
4. Migración de:
   - Usuarios (tabla usuarios → User + asignación a grupo 3 "Therapists")
   - Pacientes (clientes + infoclientes → Patient + PatientClinicalNote)
   - Tutores (creados dinámicamente → User + asignación a grupo 5 "Tutors")
   - Notas clínicas (áreas de infoclientes)
   - Pagos (pagos → Payment)
   - Sesiones (ciclos → Session)
   - Planes de intervención (plandeintervencions con recursos/énfasis agregados)
   - Escalas y evaluaciones (matrizescalas + demucas → Scale + ScaleEvaluation)
5. Rollback (si --dry-run) o commit de transacción
```

## 💡 Ejemplos de Uso

### Test (Dry-Run) Contra BD Local

Perfecto para validar antes de migrar datos reales:

```bash
python manage.py importar_laravel \
  --host legacy_mariadb \
  --user hmusicot \
  --password 'GI8}(&Fg~5J;' \
  --database hmusicot_musicoterapiadb \
  --port 3306 \
  --dry-run
```

**Resultado**: ETL ejecuta completamente y hace rollback al final. Inspecciona logs sin afectar la DB.

### Migración Completa (Primero Limpiar)

Para reimigrar desde cero:

```bash
python manage.py importar_laravel \
  --host legacy_mariadb \
  --user hmusicot \
  --password 'GI8}(&Fg~5J;' \
  --database hmusicot_musicoterapiadb \
  --port 3306 \
  --truncate
```

**Resultado**: Limpia todos los datos migrados previos y carga nuevamente.

### Contra BD Remota (Conexión Directa)

Si tienes acceso TCP directo:

```bash
python manage.py importar_laravel \
  --host cpanel.musicoterapiabolivia.com \
  --user hmusicot \
  --password 'TU_PASSWORD' \
  --database hmusicot_musicoterapiadb \
  --port 3306 \
  --dry-run
```

### Contra BD Remota con SSH Tunnel

Si la conexión directa está bloqueada, el comando intentará automáticamente SSH tunnel (si `sshtunnel` está instalado):

```bash
# Asegúrate de que la clave SSH esté en ~/.ssh/id_rsa
python manage.py importar_laravel \
  --host cpanel.musicoterapiabolivia.com \
  --user hmusicot \
  --password 'TU_PASSWORD' \
  --database hmusicot_musicoterapiadb \
  --port 3306
```

## 🔍 Verificar Migración

Después de ejecutar, verifica los datos en Django shell:

```bash
python manage.py shell
```

```python
from users.models import User
from clinical.models import Patient, PlanStep
from finance.models import Payment
from therapeutic_sessions.models import Session
from evaluations.models import Scale

# Usuarios
print(f"Usuarios legacy: {User.objects.filter(username__startswith='legacy_user_').count()}")
print(f"Tutores legacy: {User.objects.filter(username__startswith='legacy_tutor_').count()}")

# Pacientes
print(f"Pacientes: {Patient.objects.count()}")

# Planes de intervención
print(f"PlanSteps: {PlanStep.objects.count()}")
print(f"Con recursos musicales: {PlanStep.objects.exclude(musical_resources__isnull=True).exclude(musical_resources='').count()}")
print(f"Con énfasis musical: {PlanStep.objects.exclude(musical_emphasis__isnull=True).exclude(musical_emphasis='').count()}")

# Pagos
print(f"Pagos: {Payment.objects.count()}")

# Sesiones
print(f"Sesiones: {Session.objects.count()}")

# Escalas
print(f"Escalas: {Scale.objects.count()}")
```

## ⚙️ Mapeo de Datos

### Usuarios

| Legacy | Django User | Grupo | Regla |
|--------|-------------|-------|-------|
| `usuarios.id` | `username = legacy_user_{id}` | 3 (Therapists) | Usuarios de la tabla usuarios |
| Generado | `username = legacy_tutor_{id}` | 5 (Tutors) | Tutores creados dinámicamente |

### Pacientes

| Legacy | Django Patient |
|--------|-----------------|
| `clientes.id` | `ci` (PK única) |
| `clientes.nombres + apellidos` | `first_name + last_name` |
| `clientes.fechnac` | `birth_date` |
| `infoclientes.diagnostico` | `diagnosis` |

### Planes de Intervención

| Legacy | Django PlanStep |
|--------|-----------------|
| `plandeintervencions.id` | `id` |
| `plandeintervencions.momento` | `moment` (enum) |
| `plandeintervencions.objetivo` | `objective` |
| `plandeintervencions.foco` | `focus` |
| `plandeintervencions.mlt` | `approach` |
| `plandeintervencions.enfoque` | `mlt_method` |
| Agregado de `subplandeintervencions` | `musical_resources` (GROUP_CONCAT) |
| Agregado de `subplandeintervencions` | `musical_emphasis` (GROUP_CONCAT) |

### Sesiones

| Legacy | Django Session |
|--------|-----------------|
| `ciclos.id_pagos` | FK a `Payment` |
| `ciclos.num_ciclo` | `cycle_number` |
| `ciclos.num_sesion` | `session_number` |
| `ciclos.fecha_sesion` | `session_date` |

## ❌ Solución de Problemas

### Error: "Unknown MySQL server host"

**Causa**: El host legacy no es accesible desde el contenedor.

**Solución**:
1. Crear BD local con contenedor: Ver sección "Preparar la BD Legacy"
2. O verificar conectividad: `docker exec django_backend ping -c 1 legacy_mariadb`

### Error: "Access denied for user"

**Causa**: Credenciales incorrectas.

**Solución**: Verifica usuario y contraseña con:
```bash
docker exec legacy_mariadb mysql -uhmusicot -p'GI8}(&Fg~5J;' -e "SELECT 1;"
```

### Error: "value too long for type character varying(50)"

**Causa**: Datos legacy más largos que la BD destino.

**Solución**: El comando trunca automáticamente. Si aún falla, verifica los límites en `models.py`.

### Migración lenta

**Causa**: BD remota lejana o red lenta.

**Solución**:
1. Usar BD local (`legacy_mariadb` container)
2. Ejecutar `--dry-run` primero sin `--truncate` para confirmar sintaxis

### Pagos no migran (Payments migrados: 0)

**Causa**: Query de pagos simplificado requiere datos en tabla `pagos` directamente.

**Verificar**:
```bash
docker exec legacy_mariadb mysql -uhmusicot -p'GI8}(&Fg~5J;' \
  -D hmusicot_musicoterapiadb \
  -e "SELECT COUNT(*) FROM pagos;"
```

Si el conteo es > 0 y aún así no migra, revisa si `id_infocliente` existe en la tabla.

## 📊 Estadísticas Esperadas (Backup Actual)

Basado en el backup `lagacy.sql`:

| Tabla/Modelo | Registros |
|--------------|-----------|
| Usuarios legacy | 8 |
| Tutores legacy | 161+ |
| Pacientes | 173 |
| Notas clínicas | 173+ |
| Pagos | 0 (actualmente) |
| Sesiones | ~2417 |
| PlanSteps | 163 |
| Escalas | 15 |
| Respuestas evaluación | ~4560 |

## 🔐 Seguridad

- **Contraseñas**: Nunca commitees credenciales. Usa variables de entorno:
  ```bash
  export DB_PASSWORD='tu_password'
  python manage.py importar_laravel --password "$DB_PASSWORD"
  ```

- **SSH Tunnel**: El comando usa `sshtunnel` cuando falla conexión TCP. Asegura que tu clave SSH esté en `~/.ssh/id_rsa`.

- **Backup**: Siempre haz backup de la BD destino antes de `--truncate`:
  ```bash
  pg_dump tu_db > backup_$(date +%Y%m%d_%H%M%S).sql
  ```

## 📝 Notas Importantes

1. **Transacción Atómica**: Toda la migración es una sola transacción. Si algo falla, TODO se revierte.
2. **Idempotencia Parcial**: Algunos modelos usan `update_or_create`, otros `create`. Ten cuidado al re-ejecutar sin `--truncate`.
3. **Passwords Forzados**: Todos los usuarios legacy reciben `is_active=True` y una contraseña aleatoria de 16 caracteres (token). Requieren reset.
4. **Grupos Automáticos**: Usuarios legacy van a grupo 3, tutores a grupo 5. Si no existen, se crean automáticamente.

## 🆘 Contacto / Debugging

Para logs detallados, ejecuta con output verbose:

```bash
python manage.py importar_laravel --host ... --verbosity 2
```

Revisa el archivo `manage.py` si necesitas depuración adicional o modifica `_query_remote_db()` para ajustar mapeos específicos.
