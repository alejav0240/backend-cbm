from __future__ import annotations

import html
import re
import secrets
from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

import mysql.connector

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, IntegrityError
from django.contrib.auth.models import Group
from django.utils import timezone

from clinical.models import InterventionPlan, Patient, PatientClinicalNote, PlanStep
from evaluations.models import Scale, ScaleEvaluation, ScaleEvaluationSubscaleResponse, Subscale
from finance.models import Discount, Payment
from therapeutic_sessions.models import Session
from users.models import User


NULL_TOKENS = {"", "null", "none", "nil", "n/a", "na"}
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


class Command(BaseCommand):
    help = "ETL desde base de datos legacy Laravel (MariaDB) hacia modelos Django."

    def add_arguments(self, parser):
        parser.add_argument(
            "--host",
            default="cpanel.musicoterapiabolivia.com",
            help="Host de la base de datos remota (default: cpanel.musicoterapiabolivia.com).",
        )
        parser.add_argument(
            "--user",
            default="hmusicot",
            help="Usuario de la base de datos remota (default: hmusicot).",
        )
        parser.add_argument(
            "--password",
            default="",
            help="Contraseña de la base de datos remota (requerida si no está en ENV).",
        )
        parser.add_argument(
            "--database",
            default="hmusicot_musicoterapiadb",
            help="Base de datos remota (default: hmusicot_musicoterapiadb).",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=3306,
            help="Puerto de la base de datos remota (default: 3306 para MySQL).",
        )
        parser.add_argument(
            "--truncate",
            action="store_true",
            help="Limpia datos migrados y vuelve a cargar (ideal para repetir la migracion).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Ejecuta todo el ETL y hace rollback al final.",
        )

    def handle(self, *args, **options):
        # Configuración de conexión remota
        config = {
            "host": options["host"],
            "user": options["user"],
            "password": options["password"],
            "database": options["database"],
            "port": options["port"],
            "connect_timeout": 30,
        }

        self.stdout.write(self.style.NOTICE(f"Conectando a {config['host']}:{config['port']} / {config['database']}..."))
        try:
            conn_remote = self._connect_remote_db(config)
        except mysql.connector.Error as err:
            raise CommandError(f"Error de conexión a base de datos remota: {err}")

        # Leer tablas desde BD remota
        try:
            datasets = {
                "usuarios": self._query_remote_db(conn_remote, "usuarios"),
                "clientes": self._query_remote_db(conn_remote, "clientes"),
                "infoclientes": self._query_remote_db(conn_remote, "infoclientes"),
                "pagos": self._query_remote_db(conn_remote, "pagos"),
                "archivospagos": self._query_remote_db(conn_remote, "archivospagos"),
                "ciclos": self._query_remote_db(conn_remote, "ciclos"),
                "plandeintervencions": self._query_remote_db(conn_remote, "plandeintervencions"),
                # subplandeintervencions ya está agregado en el query de plandeintervencions
                "matrizescalas": self._query_remote_db(conn_remote, "matrizescalas"),
                "submatrizescalas": self._query_remote_db(conn_remote, "submatrizescalas"),
                "demucas": self._query_remote_db(conn_remote, "demucas"),
            }
        finally:
            conn_remote.close()

        dry_run = options["dry_run"]

        self.stdout.write(self.style.NOTICE("Iniciando ETL legacy..."))

        with transaction.atomic():
            if options["truncate"]:
                self._truncate_imported_data()

            therapist = self._ensure_default_therapist()
            self.stdout.write(self.style.NOTICE(f"Terapeuta por defecto: user_id={therapist.id}"))

            users_by_name = self._import_users(datasets["usuarios"])
            patients_by_legacy_client, info_map = self._import_patients_and_info(
                datasets["clientes"],
                users_by_name,
                therapist,
            )
            payment_proofs = self._extract_payment_proofs(datasets["archivospagos"])
            payments_by_legacy = self._import_payments(
                datasets["pagos"],
                info_map,
                payment_proofs,
            )
            self._import_sessions(datasets["ciclos"], payments_by_legacy, therapist)
            self._import_intervention_plans(
                datasets["plandeintervencions"],
                info_map,
                therapist,
            )
            self._import_scales_and_evaluations(
                datasets["matrizescalas"],
                datasets["submatrizescalas"],
                datasets["demucas"],
                info_map,
                therapist,
            )

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("Dry-run activo: se hizo rollback de todos los cambios."))
                return

        self.stdout.write(self.style.SUCCESS("ETL completado."))

    def _connect_remote_db(self, config):
        """Conecta a la base de datos remota MariaDB."""
        try:
            conn = mysql.connector.connect(**config)
            self.stdout.write(self.style.SUCCESS(f"Conexión exitosa a {config['host']}"))
            return conn
        except mysql.connector.Error as err:
            self.stdout.write(self.style.ERROR(f"Error de conexión: {err}"))
            raise

    def _query_remote_db(self, connection, table_name):
        """Consulta una tabla remota y retorna lista de listas (para compatibilidad con acceso por índice)."""
        # Mapeo de columnas por tabla (en el mismo orden que estaban en los CSVs)
        column_mappings = {
            "usuarios": [
                "id", "nombre", "apellido", "email", "empresa", "celular", "foto", "ci", 
                "foto_grande", "estado", "password", "ciudad", "created_at", "visible", "updated_at", "remember_token"
            ],
            # NOTA: Para clientes, hacemos JOIN con infoclientes (ver _query_clientes_with_info)
            "clientes": [
                "cli_id", "cli_nombres", "cli_apellidos", "cli_carnet", "cli_fechnac", "cli_foto", 
                "inf_notas", "inf_diagnostico", "inf_residenciaactual", "inf_tutor", "cli_usuario", 
                "cli_celular", "inf_objgenerales", "inf_social", "inf_cognitivo", "inf_fisico", 
                "inf_emocional", "inf_metodosausar", "inf_cuestionario"
            ],
            "infoclientes": [
                "id", "id_cliente", "diagnostico", "residencia", "notas", "telefonoresponsable", 
                "nombreresponsable", "tutor", "objetivo_general", "area_fisica", "area_emocional",
                "area_cognitiva", "area_social", "metodologia", "notas", "encuesta", 
                "historia_clinica", "created_at", "updated_at"
            ],
            "pagos": [
                "id", "id_infocliente", "monto_total", "fecha_pago", "monto_pagado", "observaciones",
                "created_at", "updated_at", "metodo_pago", "referencia", "id_usuarios"
            ],
            "archivospagos": [
                "id", "id_pagos", "archivo", "descripcion", "created_at", "ruta", "updated_at", 
                "detalles", "notas", "user_id"
            ],
            "ciclos": [
                "id", "id_pagos", "num_ciclo", "num_sesion", "estado_sesion", "fecha_sesion",
                "estado_pago", "eri", "cim", "ejecucion", "apuntes", "created_at", "updated_at"
            ],
            "plandeintervencions": [
                "id", "orden", "id_infocliente", "momento", "objetivo", "enfoque", "metodologia",
                "indicaciones", "duracion", "notas", "created_at"
            ],
            "subplandeintervencions": [
                "id", "id_plandeintervencions", "categoria", "descripcion", "created_at", "updated_at"
            ],
            "matrizescalas": [
                "id", "categoria", "nombre_subescala", "valor_maximo", "created_at", "updated_at", "descripcion"
            ],
            "submatrizescalas": [
                "id", "id_matrizescalas", "subescala", "nombre_subescala", "created_at", "updated_at"
            ],
            "demucas": [
                "id", "id_infocliente", "nombre_evaluacion", "date_formato", "nombre_subescala", 
                "escala", "multiplicar", "created_at", "categoria_escala", "notas", "user_id"
            ],
        }

        columns = column_mappings.get(table_name, [])

        def pick(row_dict, *keys):
            for key in keys:
                if key in row_dict and row_dict.get(key) is not None:
                    return str(row_dict.get(key))
            return ""
        
        try:
            cursor = connection.cursor(dictionary=True)
            
            # Caso especial: clientes requiere JOIN con infoclientes
            if table_name == "clientes":
                query = """
                    SELECT 
                        cli.id AS cli_id,
                        cli.nombres AS cli_nombres,
                        cli.apellidos AS cli_apellidos,
                        cli.carnet AS cli_carnet,
                        cli.fechnac AS cli_fechnac,
                        cli.foto AS cli_foto,
                        cli.usuario AS cli_usuario,
                        cli.celular AS cli_celular,
                        inf.notas AS inf_notas,
                        inf.diagnostico AS inf_diagnostico,
                        inf.residenciaactual AS inf_residenciaactual,
                        COALESCE(inf.tutor, CONCAT('TUTOR ', cli.nombres)) AS inf_tutor,
                        inf.objgenerales AS inf_objgenerales,
                        inf.social AS inf_social,
                        inf.cognitivo AS inf_cognitivo,
                        inf.fisico AS inf_fisico,
                        inf.emocional AS inf_emocional,
                        inf.metodosausar AS inf_metodosausar,
                        inf.cuestionario AS inf_cuestionario
                    FROM clientes cli
                    LEFT JOIN infoclientes inf ON cli.id = inf.id_cliente
                """
            elif table_name == "pagos":
                # Query simple para pagos; compatibilidad manejada por pick()
                query = "SELECT * FROM pagos"
            elif table_name == "plandeintervencions":
                # Query optimizado que trae main_objective, order_index, moment, objetivo, focus, mlt, approach, duration
                # y agrupa automáticamente los recursos musicales y énfasis musical
                query = """
                    SELECT
                        pi.id,
                        COALESCE(inf.objgenerales, 'Objetivo migrado desde legacy') AS main_objective,
                        pi.orden AS order_index,
                        inf.id_cliente,
                        pi.momento AS moment,
                        pi.objetivo AS objective,
                        pi.foco AS focus,
                        pi.mlt AS mlt_method,
                        pi.enfoque AS approach,
                        pi.duracion AS duration_minutes,
                        (SELECT GROUP_CONCAT(sp.nombre SEPARATOR ' | ')
                         FROM subplandeintervencions sp
                         WHERE sp.categoria = 'RECURSOS MUSICALES'
                           AND sp.id_plandeintervencion = pi.id) AS musical_resources,
                        (SELECT GROUP_CONCAT(sp.nombre SEPARATOR ' | ')
                         FROM subplandeintervencions sp
                         WHERE sp.categoria = 'ENFASIS MUSICAL'
                           AND sp.id_plandeintervencion = pi.id) AS musical_emphasis,
                        pi.created_at,
                        pi.updated_at
                    FROM plandeintervencions pi
                    INNER JOIN infoclientes inf ON pi.id_infocliente = inf.id
                """
            elif table_name == "usuarios":
                query = """
                    SELECT
                        id,
                        nombres AS first_name,
                        apellidos AS last_name,
                        usuario AS legacy_username,
                        celulartrabajo AS celular,
                        celular AS celular_opcional,
                        carnet AS ci,
                        visibilidad
                    FROM usuarios
                """
            else:
                query = f"SELECT * FROM {table_name}"
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            # Convertir diccionarios a listas ordenadas por columnas conocidas
            result = []
            for row in rows:
                # Compatibilidad con variantes de esquema legacy (backup local vs nube)
                if table_name == "pagos":
                    # Nueva estructura: patient_id, price_per_session, amount_paid, payment_type, descuento
                    row_list = [
                        pick(row, "patient_id"),
                        pick(row, "price_per_session"),
                        pick(row, "amount_paid"),
                        pick(row, "payment_type"),
                        pick(row, "descuento"),
                    ]
                elif table_name == "pagos_legacy":  # Para compatibilidad con query antiguo
                    row_list = [
                        pick(row, "id"),
                        pick(row, "id_infocliente"),
                        pick(row, "monto_total", "precio"),
                        pick(row, "fecha_pago", "fecha"),
                        pick(row, "monto_pagado", "pagado"),
                        pick(row, "observaciones", "horario"),
                        pick(row, "created_at"),
                        pick(row, "updated_at"),
                        pick(row, "metodo_pago", "tipo"),
                        pick(row, "referencia", "descuento"),
                        pick(row, "id_usuarios"),
                    ]
                elif table_name == "usuarios":
                    # Query explícita para usuarios; mantenemos compatibilidad con el layout viejo.
                    row_list = [
                        pick(row, "id"),
                        pick(row, "first_name", "nombres", "nombre"),
                        pick(row, "last_name", "apellidos", "apellido"),
                        pick(row, "legacy_username", "usuario", "email"),
                        pick(row, "celular", "celulartrabajo"),
                        pick(row, "celular_opcional"),
                        pick(row, "ci", "carnet"),
                        pick(row, "visibilidad", "visible"),
                        pick(row, "estado"),
                        pick(row, "foto"),
                        pick(row, "created_at"),
                        pick(row, "updated_at"),
                    ]
                    
                elif table_name == "archivospagos":
                    row_list = [
                        pick(row, "id"),
                        pick(row, "id_pagos", "id_pago"),
                        pick(row, "archivo", "monto"),
                        pick(row, "descripcion", "fechapago"),
                        pick(row, "created_at", "horapago"),
                        pick(row, "ruta", "file"),
                        pick(row, "updated_at", "observacion"),
                        pick(row, "detalles", "estadopago"),
                        pick(row, "notas", "created_at"),
                        pick(row, "user_id", "updated_at"),
                    ]
                elif table_name == "plandeintervencions":
                    # Query optimizado: ya tiene main_objective, order_index, momento, objetivo, focus, mlt, approach, duration
                    # y los recursos musicales y énfasis musical pre-agregados
                    row_list = [
                        pick(row, "id"),
                        pick(row, "order_index"),
                        pick(row, "id_cliente"),  # legacy_info_id
                        pick(row, "moment"),
                        pick(row, "objective"),
                        pick(row, "focus"),
                        pick(row, "mlt_method"),
                        pick(row, "approach"),
                        pick(row, "duration_minutes"),
                        pick(row, "main_objective"),
                        pick(row, "musical_resources"),
                        pick(row, "musical_emphasis"),
                        pick(row, "created_at"),
                        pick(row, "updated_at"),
                    ]
                elif table_name == "ciclos":
                    row_list = [
                        pick(row, "id"),
                        pick(row, "id_pagos", "id_pago"),
                        pick(row, "num_ciclo", "nrociclo"),
                        pick(row, "num_sesion", "sesion"),
                        pick(row, "estado_sesion", "estadosesion"),
                        pick(row, "fecha_sesion", "fecha"),
                        pick(row, "estado_pago", "estadopago"),
                        pick(row, "eri"),
                        pick(row, "cim"),
                        pick(row, "ejecucion"),
                        pick(row, "apuntes"),
                        pick(row, "created_at"),
                        pick(row, "updated_at"),
                    ]
                elif columns:
                    # Usar mapeo conocido de columnas
                    row_list = [str(row.get(col, "")) for col in columns]
                else:
                    # Fallback: si no hay mapeo, convertir diccionario a lista de valores
                    row_list = [str(v) if v is not None else "" for v in row.values()]
                result.append(row_list)
            
            self.stdout.write(self.style.SUCCESS(f"Tabla '{table_name}': {len(result)} registros."))
            cursor.close()
            return result
        except mysql.connector.Error as err:
            self.stdout.write(self.style.ERROR(f"Error consultando '{table_name}': {err}"))
            raise

    def _truncate_imported_data(self):
        self.stdout.write(self.style.WARNING("--truncate activo: limpiando datos migrados."))
        ScaleEvaluationSubscaleResponse.objects.all().delete()
        ScaleEvaluation.objects.all().delete()
        Subscale.objects.all().delete()
        Scale.objects.all().delete()

        PlanStep.objects.all().delete()
        InterventionPlan.objects.all().delete()

        Session.objects.all().delete()
        Payment.objects.all().delete()
        PatientClinicalNote.objects.all().delete()
        Patient.objects.all().delete()

        User.objects.filter(username__startswith="legacy_user_").delete()
        User.objects.filter(username__startswith="legacy_tutor_").delete()

    def _ensure_default_therapist(self) -> User:
        therapist = User.objects.filter(id=1).first()
        if therapist:
            return therapist

        # Fallback seguro si no existe id=1 en este ambiente.
        therapist = User.objects.filter(is_superuser=True).order_by("id").first()
        if therapist:
            return therapist

        therapist, _ = User.objects.get_or_create(
            username="legacy_admin_1",
            defaults={
                "first_name": "Legacy",
                "last_name": "Admin",
                "ci": "LEGACY-ADMIN-1",
                "status": "active",
                "visibility": "public",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        therapist.set_password(secrets.token_urlsafe(16))
        therapist.save(update_fields=["password"])
        return therapist

    def _import_users(self, rows):
        users_by_name = {}
        created_count = 0
        updated_count = 0

        for row in rows:
            if len(row) < 8:
                continue

            legacy_id = self._to_int(row[0])
            first_name = self._limit_text(self._clean_text(row[1]), 150)
            last_name = self._limit_text(self._clean_text(row[2]), 150)

            if len(row) >= 12:
                celular = self._limit_text(self._clean_text(row[4]), 20)
                ci = self._limit_text(self._clean_text(row[6]), 50)
                visibilidad = self._clean_text(row[7]).lower()
                estado = self._clean_text(row[8]).lower()
                foto = self._clean_text(row[9]) or None
            else:
                celular = self._limit_text(self._clean_text(row[4]), 20)
                ci = self._limit_text(self._clean_text(row[6]), 50)
                visibilidad = self._clean_text(row[7]).lower()
                estado = "activo"
                foto = None

            ci = ci or f"LEGACY-USR-{legacy_id}"

            username = f"legacy_user_{legacy_id}"
            defaults = {
                "first_name": first_name,
                "last_name": last_name,
                "ci": ci,
                "celular": celular,
                "status": "active" if estado == "activo" else "inactive",
                "visibility": "public" if visibilidad in {"visible", "si", "yes"} else "private",
                "foto": foto,
                "is_active": True,
            }

            user, created = User.objects.update_or_create(username=username, defaults=defaults)
            user.set_password(secrets.token_urlsafe(16))
            user.save(update_fields=["password"])

            # Asignar al grupo de terapeutas (group id 3)
            try:
                group_therapist = self._get_or_create_group(3, "Therapists")
                user.groups.add(group_therapist)
            except Exception:
                # No interrumpir la migración por problemas de grupos
                pass

            full_name_key = self._normalize_name(f"{first_name} {last_name}")
            users_by_name[full_name_key] = user

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Users migrados: creados={created_count}, actualizados={updated_count} (password reset forzado)."
            )
        )
        return users_by_name

    def _import_patients_and_info(self, clientes_rows, users_by_name, default_therapist):
        """
        Import patients from legacy with clinical info already joined.
        Structure (from JOIN clientes LEFT JOIN infoclientes):
        0: cli_id, 1: cli_nombres, 2: cli_apellidos, 3: cli_carnet, 4: cli_fechnac, 
        5: cli_foto, 6: inf_notas, 7: inf_diagnostico, 8: inf_residenciaactual, 
        9: inf_tutor (fullname with fallback), 10: cli_usuario, 11: cli_celular,
        12: inf_objgenerales, 13: inf_social, 14: inf_cognitivo, 15: inf_fisico, 
        16: inf_emocional, 17: inf_metodosausar, 18: inf_cuestionario
        """
        patients_by_legacy_client = {}
        info_map = {}

        for row in clientes_rows:
            if len(row) < 19:
                continue

            legacy_client_id = self._to_int(row[0])
            first_name = self._limit_text(self._clean_text(row[1]), 100)
            last_name = self._limit_text(self._clean_text(row[2]), 100)
            ci_raw = self._clean_text(row[3])
            ci = self._limit_text(ci_raw if ci_raw and ci_raw not in {"0", "0000"} else f"LEGACY-PAT-{legacy_client_id}", 30)
            birth_date = self._to_date(row[4])
            image_url = self._clean_text(row[5]) or None
            
            # From infoclientes (LEFT JOIN)
            notes = self._clean_text(row[6])
            diagnosis = self._limit_text(self._clean_text(row[7]), 50)
            residence = self._limit_text(self._clean_text(row[8]), 100)
            tutor_fullname = self._clean_text(row[9])
            
            # Clinical note fields (areas)
            general_objective = self._clean_text(row[12])
            social = self._clean_text(row[13])
            cognitive = self._clean_text(row[14])
            physical = self._clean_text(row[15])
            emotional = self._clean_text(row[16])
            methods = self._clean_text(row[17])
            questionnaire = self._clean_text(row[18])
            
            status = Patient.Status.ACTIVE  # Default status

            patient, _ = Patient.objects.update_or_create(
                ci=ci,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "birth_date": birth_date,
                    "image_url": image_url,
                    "status": status,
                    "diagnosis": diagnosis,
                    "residence": residence,
                    "notes": notes,
                    "registration_complete": True,
                },
            )
            patients_by_legacy_client[legacy_client_id] = patient

            # Resolve or create tutor user
            tutor_user = self._resolve_or_create_tutor_user(legacy_client_id, tutor_fullname, users_by_name)
            patient.tutor = tutor_user
            patient.save(update_fields=["tutor", "updated_at"])

            # Create clinical notes from areas
            self._upsert_clinical_note(patient, default_therapist, "GENERAL_OBJECTIVE", general_objective)
            self._upsert_clinical_note(patient, default_therapist, "PHYSICAL_AREA", physical)
            self._upsert_clinical_note(patient, default_therapist, "EMOTIONAL_AREA", emotional)
            self._upsert_clinical_note(patient, default_therapist, "COGNITIVE_AREA", cognitive)
            self._upsert_clinical_note(patient, default_therapist, "SOCIAL_AREA", social)
            self._upsert_clinical_note(patient, default_therapist, "METHODS", methods)
            self._upsert_clinical_note(patient, default_therapist, "ADDITIONAL_NOTES", questionnaire)

            info_map[legacy_client_id] = {
                "patient": patient,
                "tutor_user": tutor_user,
            }

        self.stdout.write(self.style.SUCCESS(f"Patients migrados: {len(patients_by_legacy_client)}"))
        self.stdout.write(self.style.SUCCESS(f"InfoClinica migrada: {len(info_map)}"))
        return patients_by_legacy_client, info_map

    def _resolve_or_create_tutor_user(self, legacy_info_id, tutor_name, users_by_name):
        key = self._normalize_name(tutor_name)
        if key and key in users_by_name:
            return users_by_name[key]

        first_name, last_name = self._split_name(tutor_name)
        username = f"legacy_tutor_{legacy_info_id}"

        tutor_user, _ = User.objects.update_or_create(
            username=username,
            defaults={
                "first_name": self._limit_text(first_name, 150),
                "last_name": self._limit_text(last_name, 150),
                "ci": self._limit_text(f"LEGACY-TUTOR-{legacy_info_id}", 50),
                "celular": "",
                "status": "active",
                "visibility": "private",
                "is_active": True,
            },
        )
        tutor_user.set_password(secrets.token_urlsafe(16))
        tutor_user.save(update_fields=["password"])

        # Asignar al grupo de tutores (group id 5)
        try:
            group_tutor = self._get_or_create_group(5, "Tutors")
            tutor_user.groups.add(group_tutor)
        except Exception:
            pass

        users_by_name[key] = tutor_user
        return tutor_user

    def _upsert_clinical_note(self, patient, author, category, content):
        if not content:
            return

        note, _ = PatientClinicalNote.objects.get_or_create(
            patient=patient,
            category=category,
            defaults={"author": author, "content": content},
        )
        if note.content != content:
            note.author = author
            note.content = content
            note.save(update_fields=["author", "content"])

    def _extract_payment_proofs(self, rows):
        proof_by_payment_id = {}
        for row in rows:
            if len(row) < 10:
                continue
            legacy_payment_id = self._to_int(row[1])
            file_path = self._clean_text(row[5])
            if file_path:
                proof_by_payment_id[legacy_payment_id] = file_path
        return proof_by_payment_id

    def _import_payments(self, rows, info_map, payment_proofs):
        payments_by_legacy = {}
        imported = 0
        
        # Mapeo de descuentos: 50 → id 1, 25 → id 2
        discount_mapping = {
            "50": 1,
            "25": 2,
        }

        for row in rows:
            # Estructura del query: patient_id, price_per_session, amount_paid, payment_type, descuento
            if len(row) < 5:
                continue

            # Buscar el patient_id en los datos que vinieron (this es el cli.id del JOIN)
            # Necesitamos mapear esto de vuelta al legacy_info_id
            # Por ahora usamos la relación que ya existe en info_map

            patient_id = self._to_int(row[0])
            price_per_session = self._to_decimal(row[1], Decimal("0"))
            amount_paid = self._to_decimal(row[2], Decimal("0"))
            payment_type_raw = self._clean_text(row[3]).lower()
            descuento_raw = self._clean_text(row[4])

            # Encontrar el patient en info_map por patient_id
            patient = None
            for legacy_info_id, info in info_map.items():
                if info["patient"].id == patient_id:
                    patient = info["patient"]
                    break

            if not patient:
                continue

            # Mapear tipo (mensual → therapy_monthly, sesion → therapy_session)
            if "mensual" in payment_type_raw:
                payment_type = Payment.PaymentType.THERAPY_MONTHLY
                sessions_count = 1  # Para planes mensuales
            elif "sesion" in payment_type_raw:
                payment_type = Payment.PaymentType.THERAPY_SESSION
                sessions_count = 1  # Se determinará por ciclos si existe
            else:
                payment_type = Payment.PaymentType.THERAPY_SESSION
                sessions_count = 1

            # Mapear descuento
            discount = None
            if descuento_raw and descuento_raw != "0":
                discount_id = discount_mapping.get(descuento_raw)
                if discount_id:
                    try:
                        discount = Discount.objects.get(id=discount_id)
                    except Discount.DoesNotExist:
                        pass

            # Determinar método de pago (si existe comprobante → QR, sino → CASH)
            payment_proof_url = payment_proofs.get(patient.id)
            payment_method = (
                Payment.PaymentMethod.QR if payment_proof_url else Payment.PaymentMethod.CASH
            )

            # Por defecto, todos los pagos migrados se marcan como COMPLETED
            payment_status = Payment.PaymentStatus.COMPLETED

            payment = Payment.objects.create(
                patient=patient,
                discount=discount,
                sessions_count=sessions_count,
                price_per_session=price_per_session,
                amount_paid=amount_paid,
                payment_method=payment_method,
                payment_proof_url=payment_proof_url,
                payment_status=payment_status,
                payment_type=payment_type,
            )

            payments_by_legacy[patient.id] = payment
            imported += 1

        self.stdout.write(self.style.SUCCESS(f"Payments migrados: {imported}"))
        return payments_by_legacy

    def _import_sessions(self, rows, payments_by_legacy, therapist):
        imported = 0
        for row in rows:
            if len(row) < 13:
                continue

            legacy_payment_id = self._to_int(row[1])
            payment = payments_by_legacy.get(legacy_payment_id)
            if not payment:
                continue

            session_date = self._to_date(row[5]) or timezone.now().date()
            session_datetime = timezone.make_aware(datetime.combine(session_date, time(12, 0)))
            session_number = self._to_int(row[3], 0)
            cycle_number = self._to_int(row[2], 0)
            session_status = self._map_session_status(row[4])
            payment_status = self._map_session_payment_status(row[6])

            eri = self._clean_text(row[7])
            cim = self._clean_text(row[8])
            ejecucion = self._clean_text(row[9])
            apuntes = self._clean_text(row[10])
            notes_parts = [p for p in [f"ERI: {eri}" if eri else "", f"CIM: {cim}" if cim else "", ejecucion, apuntes] if p]
            notes = "\n".join(notes_parts) if notes_parts else None

            Session.objects.create(
                patient=payment.patient,
                therapist=therapist,
                group=None,
                session_date=session_datetime,
                session_type=Session.SessionType.INDIVIDUAL,
                session_status=session_status,
                session_number=session_number,
                duration_minutes=None,
                cycle_number=cycle_number,
                notes=notes,
                payment_status=payment_status,
            )
            imported += 1

        self.stdout.write(self.style.SUCCESS(f"Sessions migradas: {imported}"))

    def _import_intervention_plans(self, plan_rows, info_map, created_by):
        """Import intervention plans and steps from optimized query that aggregates subplans.
        
        Structure (from optimized query):
        0: id, 1: order_index, 2: id_cliente (legacy_info_id), 3: moment, 4: objective,
        5: focus, 6: mlt_method, 7: approach, 8: duration_minutes, 9: main_objective,
        10: musical_resources (pre-aggregated), 11: musical_emphasis (pre-aggregated),
        12: created_at, 13: updated_at
        """
        plan_by_patient = {}
        imported_steps = 0

        for row in plan_rows:
            if len(row) < 14:
                continue

            legacy_plan_id = self._to_int(row[0])
            order_index = self._to_int(row[1], 0)
            legacy_info_id = self._to_int(row[2])
            info = info_map.get(legacy_info_id)
            if not info:
                continue

            patient = info["patient"]
            plan = plan_by_patient.get(patient.id)
            if not plan:
                main_objective = self._limit_text(self._clean_text(row[9]) or "Objetivo migrado desde legacy", 500)
                plan = InterventionPlan.objects.create(
                    patient=patient,
                    created_by=created_by,
                    main_objective=main_objective,
                    start_date=timezone.now().date(),
                )
                plan_by_patient[patient.id] = plan

            moment = self._map_plan_moment(row[3])
            objective = self._limit_text(self._clean_text(row[4]) or "Paso migrado", 255)
            focus = self._clean_text(row[5]) or None
            approach = self._limit_text(self._clean_text(row[6]), 255) or None
            mlt_method = self._limit_text(self._clean_text(row[7]), 100) or None
            duration_minutes = self._to_int(row[8])
            musical_resources = self._clean_text(row[10]) or None
            musical_emphasis = self._clean_text(row[11]) or None

            step = PlanStep.objects.create(
                plan=plan,
                moment=moment,
                duration_minutes=duration_minutes,
                objective=objective,
                focus=focus,
                musical_resources=musical_resources,
                musical_emphasis=musical_emphasis,
                approach=approach,
                mlt_method=mlt_method,
                order_index=order_index,
            )

            imported_steps += 1

        self.stdout.write(self.style.SUCCESS(f"PlanSteps migrados: {imported_steps}"))

    def _import_scales_and_evaluations(
        self,
        matrix_rows,
        submatrix_rows,
        demucas_rows,
        info_map,
        evaluator,
    ):
        scale_by_category = {}
        matrix_to_category = {}

        for row in matrix_rows:
            if len(row) < 7:
                continue

            legacy_matrix_id = self._to_int(row[0])
            category = self._clean_text(row[1]) or "ESCALA LEGACY"
            category = self._limit_text(category, 255)
            subscale_name = self._limit_text(self._clean_text(row[2]), 255)
            max_value = self._to_int(row[3], 5)

            scale = scale_by_category.get(category)
            if not scale:
                scale, _ = Scale.objects.get_or_create(
                    name=category,
                    defaults={
                        "description": "Migrada desde matrizescalas",
                        "scale_type": Scale.ScaleType.SUBSCALE,
                    },
                )
                scale_by_category[category] = scale

            matrix_to_category[legacy_matrix_id] = category
            if subscale_name:
                Subscale.objects.get_or_create(
                    scale=scale,
                    name=subscale_name,
                    defaults={"max_value": max(max_value, 1)},
                )

        for row in submatrix_rows:
            if len(row) < 6:
                continue

            legacy_matrix_id = self._to_int(row[1])
            subscale_name = self._limit_text(self._clean_text(row[3]), 255)
            if not subscale_name:
                continue

            category = matrix_to_category.get(legacy_matrix_id)
            if not category:
                continue

            scale = scale_by_category[category]
            Subscale.objects.get_or_create(
                scale=scale,
                name=subscale_name,
                defaults={"max_value": 5},
            )

        eval_cache = {}
        imported_responses = 0

        for row in demucas_rows:
            if len(row) < 11:
                continue

            legacy_info_id = self._to_int(row[1])
            info = info_map.get(legacy_info_id)
            if not info:
                continue

            category = self._limit_text(self._clean_text(row[8]) or "ESCALA LEGACY", 255)
            scale = scale_by_category.get(category)
            if not scale:
                scale, _ = Scale.objects.get_or_create(
                    name=category,
                    defaults={
                        "description": "Migrada desde demucas",
                        "scale_type": Scale.ScaleType.SUBSCALE,
                    },
                )
                scale_by_category[category] = scale

            subscale_name = self._limit_text(self._clean_text(row[4]) or f"ITEM-{self._to_int(row[0], 0)}", 255)
            subscale, _ = Subscale.objects.get_or_create(
                scale=scale,
                name=subscale_name,
                defaults={"max_value": 5},
            )

            score = self._score_from_legacy(row[5], row[6], subscale.max_value)
            eval_name = self._clean_text(row[2])
            eval_date = self._to_date(row[7]) or timezone.now().date()

            cache_key = (legacy_info_id, category, eval_name, eval_date.isoformat())
            evaluation = eval_cache.get(cache_key)
            if not evaluation:
                evaluation = ScaleEvaluation.objects.create(
                    scale=scale,
                    patient=info["patient"],
                    evaluator=evaluator,
                    session=None,
                )
                eval_cache[cache_key] = evaluation

            ScaleEvaluationSubscaleResponse.objects.update_or_create(
                evaluation=evaluation,
                subscale=subscale,
                defaults={"score": score},
            )
            imported_responses += 1

        self.stdout.write(self.style.SUCCESS(f"Scales migradas: {len(scale_by_category)}"))
        self.stdout.write(self.style.SUCCESS(f"Respuestas de evaluacion migradas: {imported_responses}"))

    def _clean_text(self, value):
        if value is None:
            return ""

        raw = str(value).strip()
        if raw.lower() in NULL_TOKENS:
            return ""

        # Convierte html a texto plano para cumplir la limpieza solicitada.
        raw = re.sub(r"<(br|/p|/div|/li|/tr)>", "\n", raw, flags=re.IGNORECASE)
        raw = TAG_RE.sub(" ", raw)
        raw = html.unescape(raw)
        raw = raw.replace("\xa0", " ")

        lines = [SPACE_RE.sub(" ", line).strip() for line in raw.splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines)

    def _to_int(self, value, default=None):
        cleaned = self._clean_text(value)
        if not cleaned:
            return default
        try:
            return int(float(cleaned))
        except (TypeError, ValueError):
            return default

    def _to_decimal(self, value, default=Decimal("0")):
        cleaned = self._clean_text(value)
        if not cleaned:
            return default
        cleaned = cleaned.replace(",", ".")
        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return default

    def _to_date(self, value):
        cleaned = self._clean_text(value)
        if not cleaned:
            return None

        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(cleaned, fmt).date()
            except ValueError:
                continue
        return None

    def _normalize_name(self, value):
        return SPACE_RE.sub(" ", self._clean_text(value).lower()).strip()

    def _split_name(self, full_name):
        name = self._clean_text(full_name)
        if not name:
            return "Tutor", "Legacy"
        chunks = name.split(" ", 1)
        if len(chunks) == 1:
            return chunks[0], "Legacy"
        return chunks[0], chunks[1]

    def _map_patient_status(self, legacy_status):
        value = self._clean_text(legacy_status).lower()
        if value == "activo":
            return Patient.Status.ACTIVE
        if value == "inactivo":
            return Patient.Status.INACTIVE
        return Patient.Status.PENDING

    def _map_session_status(self, legacy_status):
        value = self._clean_text(legacy_status).upper()
        mapping = {
            "REALIZADO": Session.SessionStatus.COMPLETADA,
            "CONFIRMADO": Session.SessionStatus.CONFIRMADA,
            "REPROGRAMADO": Session.SessionStatus.REPROGRAMA,
            "CANCELADO": Session.SessionStatus.CANCELADA,
        }
        return mapping.get(value, Session.SessionStatus.COMPLETADA)

    def _map_session_payment_status(self, legacy_payment_status):
        value = self._clean_text(legacy_payment_status).upper()
        if value == "PAGADO":
            return Session.PaymentStatus.PAID
        return Session.PaymentStatus.PENDING

    def _map_plan_moment(self, legacy_moment):
        value = self._clean_text(legacy_moment).lower()
        if value in {"bienvenida", "inicio", "inicial"}:
            return PlanStep.Moment.BIENVENIDA
        if value in {"relajacion", "relajacion.", "despedida", "cierre"}:
            return PlanStep.Moment.RELAJACION
        # Mapear otros valores conocidos del enum
        moment_mapping = {
            "iso": PlanStep.Moment.ISO,
            "melodico": PlanStep.Moment.MELODICO,
            "ritmico": PlanStep.Moment.RITMICO,
            "armonico": PlanStep.Moment.ARMONICO,
            "abstraccion": PlanStep.Moment.ABSTRACCION,
            "danza libre": PlanStep.Moment.DANZA_LIBRE,
            "danza_libre": PlanStep.Moment.DANZA_LIBRE,
            "expresion corporal": PlanStep.Moment.EXPRESION_CORPORAL,
            "expresion_corporal": PlanStep.Moment.EXPRESION_CORPORAL,
            "ritmo y espacio": PlanStep.Moment.RITMO_Y_ESPACIO,
            "ritmo_y_espacio": PlanStep.Moment.RITMO_Y_ESPACIO,
        }
        mapped = moment_mapping.get(value)
        if mapped:
            return mapped
        # Default a BIENVENIDA si no se reconoce
        return PlanStep.Moment.BIENVENIDA

    def _score_from_legacy(self, escala_text, multiplicar_value, max_value):
        parsed = self._to_int(multiplicar_value)
        if parsed is not None and parsed >= 0:
            return min(parsed, max_value)

        value = self._clean_text(escala_text).upper()
        mapping = {
            "NADA": 0,
            "POCO": 1,
            "BAJO": 1,
            "MEDIO": 2,
            "REGULAR": 2,
            "ALTO": 3,
            "MUCHO": 4,
        }
        if value in mapping:
            return min(mapping[value], max_value)

        parsed_scale = self._to_int(value)
        if parsed_scale is not None:
            return min(parsed_scale, max_value)

        return min(0, max_value)

    def _append_text(self, current, value):
        if not current:
            return value
        if value in current:
            return current
        return f"{current} | {value}"

    def _limit_text(self, value, max_length):
        if value is None:
            return ""
        text = str(value)
        if len(text) <= max_length:
            return text
        return text[:max_length]

    def _get_or_create_group(self, pk, name):
        """Obtiene un grupo por PK o lo crea con el id proporcionado. Si falla
        crear con PK (por restricciones), crea el grupo sin especificar PK."""
        grp = Group.objects.filter(pk=pk).first()
        if grp:
            return grp
        try:
            grp = Group.objects.create(id=pk, name=name)
            return grp
        except IntegrityError:
            # Fallback: crear sin pk explícito
            grp, _ = Group.objects.get_or_create(name=name)
            return grp

