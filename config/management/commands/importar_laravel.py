from __future__ import annotations

import html
import re
import secrets
from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

import mysql.connector
try:
    from sshtunnel import SSHTunnelForwarder
except Exception:
    SSHTunnelForwarder = None

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from clinical.models import InterventionPlan, Patient, PatientClinicalNote, PlanStep
from evaluations.models import Scale, ScaleEvaluation, ScaleEvaluationSubscaleResponse, Subscale
from finance.models import Payment
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

        ssh_tunnel = None
        # Si el usuario indicó puerto 22, intentamos crear un túnel SSH local -> remote:3306
        if options["port"] == 22:
            if SSHTunnelForwarder is None:
                self.stdout.write(self.style.WARNING("sshtunnel no está instalado; se intentará conexión SSH-fallback usando el cliente 'mysql' remoto."))
            try:
                self.stdout.write(self.style.NOTICE("Estableciendo túnel SSH (puerto 22) hacia el servidor remoto..."))
                # Intentamos varias formas de bind remoto por si el servidor usa localhost o 127.0.0.1
                tried = []
                for remote_host in ("127.0.0.1", "localhost"):
                    try:
                        ssh_tunnel = SSHTunnelForwarder(
                            (config["host"], 22),
                            ssh_username=options["user"],
                            ssh_password=options["password"],
                            remote_bind_address=(remote_host, 3306),
                            # local_bind_address=("127.0.0.1", 3307),
                        )
                        ssh_tunnel.start()
                        config["host"] = "127.0.0.1"
                        config["port"] = ssh_tunnel.local_bind_port
                        self.stdout.write(self.style.SUCCESS(f"Túnel SSH activo (remote_bind={remote_host}:3306) en localhost:{config['port']}"))
                        break
                    except Exception as e_inner:
                        tried.append((remote_host, str(e_inner)))
                        ssh_tunnel = None
                if ssh_tunnel is None:
                    self.stdout.write(self.style.WARNING(f"No se pudo establecer túnel SSH. Intentos: {tried}. Se seguirá con fallback SSH-cliente si es necesario."))
            except Exception as err:
                if ssh_tunnel:
                    try:
                        ssh_tunnel.stop()
                    except Exception:
                        pass
                self.stdout.write(self.style.WARNING(f"Excepción creando túnel SSH: {err}. Se seguirá con fallback SSH-cliente si es necesario."))

        conn_remote = None
        # Si se pidió puerto 22 y no pudimos crear un túnel SSH, usar directamente SSH+mysql remoto
        if options["port"] == 22 and ssh_tunnel is None:
            self.stdout.write(self.style.WARNING("Usando modo SSH-fallback (cliente mysql en el servidor remoto)"))
            conn_remote = {
                "ssh": True,
                "host": options["host"],
                "user": options["user"],
                "password": options["password"],
                "database": options["database"],
            }
        else:
            try:
                conn_remote = self._connect_remote_db(config)
            except mysql.connector.Error as err:
                if ssh_tunnel:
                    try:
                        ssh_tunnel.stop()
                    except Exception:
                        pass
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
                "subplandeintervencions": self._query_remote_db(conn_remote, "subplandeintervencions"),
                "matrizescalas": self._query_remote_db(conn_remote, "matrizescalas"),
                "submatrizescalas": self._query_remote_db(conn_remote, "submatrizescalas"),
                "demucas": self._query_remote_db(conn_remote, "demucas"),
            }
        finally:
            try:
                conn_remote.close()
            except Exception:
                pass
            if ssh_tunnel:
                try:
                    ssh_tunnel.stop()
                except Exception:
                    pass

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
                datasets["infoclientes"],
                users_by_name,
                therapist,
            )
            payment_proofs = self._extract_payment_proofs(datasets["archivospagos"])
            cycle_count_by_payment = self._count_cycles_by_payment(datasets["ciclos"])
            payments_by_legacy = self._import_payments(
                datasets["pagos"],
                info_map,
                payment_proofs,
                cycle_count_by_payment,
            )
            self._import_sessions(datasets["ciclos"], payments_by_legacy, therapist)
            self._import_intervention_plans(
                datasets["plandeintervencions"],
                datasets["subplandeintervencions"],
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
            "clientes": [
                "id", "nombre", "apellido", "email", "telefono", "empresa", "ciudad", "fecha_nacimiento",
                "cedula", "foto", "estado", "notas", "created_at"
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
        
        # Si la conexión es un dict con 'ssh', usamos el cliente mysql remoto via SSH
        if isinstance(connection, dict) and connection.get("ssh"):
            import subprocess

            host = connection["host"]
            user = connection["user"]
            password = connection["password"]
            database = connection["database"]

            # Construir SELECT con columnas conocidas (si están) para mantener el orden
            select_cols = ", ".join(columns) if columns else "*"
            remote_mysql_cmd = f"mysql -u {user} -p'{password}' -D {database} -N -B -e \"SELECT {select_cols} FROM {table_name};\""
            ssh_cmd = f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {user}@{host} \"{remote_mysql_cmd}\""

            try:
                # Usar sshpass para pasar la contraseña SSH si está disponible en el sistema
                full_cmd = f"sshpass -p '{password}' {ssh_cmd}"
                proc = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=60)
                if proc.returncode != 0:
                    self.stdout.write(self.style.ERROR(f"Error ejecutando query remoto '{table_name}': {proc.stderr.strip()}"))
                    raise CommandError(f"SSH/mysql remoto falló: {proc.stderr.strip()}")

                lines = [l for l in proc.stdout.splitlines() if l.strip() != ""]
                result = []
                for line in lines:
                    # mysql -B separa por tabulador
                    parts = line.split('\t')
                    row_list = [p for p in parts]
                    result.append(row_list)

                self.stdout.write(self.style.SUCCESS(f"Tabla '{table_name}': {len(result)} registros (via SSH)."))
                return result
            except Exception as err:
                self.stdout.write(self.style.ERROR(f"Error consultando '{table_name}' via SSH: {err}"))
                raise

        try:
            cursor = connection.cursor(dictionary=True)
            query = f"SELECT * FROM {table_name}"
            cursor.execute(query)
            rows = cursor.fetchall()
            
            # Convertir diccionarios a listas ordenadas por columnas conocidas
            result = []
            for row in rows:
                if columns:
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
            if len(row) < 16:
                continue

            legacy_id = self._to_int(row[0])
            first_name = self._clean_text(row[1])
            last_name = self._clean_text(row[2])
            celular = self._clean_text(row[5])
            ci = self._clean_text(row[7]) or f"LEGACY-USR-{legacy_id}"
            foto = self._clean_text(row[8]) or None
            estado = self._clean_text(row[9]).lower()
            visibilidad = self._clean_text(row[13]).lower()

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

    def _import_patients_and_info(self, clientes_rows, info_rows, users_by_name, default_therapist):
        patients_by_legacy_client = {}
        info_map = {}

        for row in clientes_rows:
            if len(row) < 13:
                continue

            legacy_client_id = self._to_int(row[0])
            first_name = self._clean_text(row[1])
            last_name = self._clean_text(row[2])
            birth_date = self._to_date(row[7])
            ci_raw = self._clean_text(row[8])
            ci = ci_raw if ci_raw and ci_raw not in {"0", "0000"} else f"LEGACY-PAT-{legacy_client_id}"
            image_url = self._clean_text(row[9]) or None
            status = self._map_patient_status(self._clean_text(row[10]))

            patient, _ = Patient.objects.update_or_create(
                ci=ci,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "birth_date": birth_date,
                    "image_url": image_url,
                    "status": status,
                },
            )
            patients_by_legacy_client[legacy_client_id] = patient

        for row in info_rows:
            if len(row) < 19:
                continue

            legacy_info_id = self._to_int(row[0])
            legacy_client_id = self._to_int(row[1])
            patient = patients_by_legacy_client.get(legacy_client_id)
            if not patient:
                continue

            tutor_name = self._clean_text(row[7])
            tutor_user = self._resolve_or_create_tutor_user(legacy_info_id, tutor_name, users_by_name)

            diagnosis = self._clean_text(row[2])
            residence = self._clean_text(row[3])
            general_objective = self._clean_text(row[9])
            physical = self._clean_text(row[10])
            emotional = self._clean_text(row[11])
            cognitive = self._clean_text(row[12])
            social = self._clean_text(row[13])
            methods = self._clean_text(row[14])
            notes = self._clean_text(row[15])
            questionnaire = self._clean_text(row[16])

            patient.tutor = tutor_user
            patient.diagnosis = diagnosis or patient.diagnosis
            patient.residence = residence or patient.residence
            patient.notes = notes or patient.notes
            patient.registration_complete = True
            patient.save(
                update_fields=["tutor", "diagnosis", "residence", "notes", "registration_complete", "updated_at"]
            )

            self._upsert_clinical_note(patient, default_therapist, "GENERAL_OBJECTIVE", general_objective)
            self._upsert_clinical_note(patient, default_therapist, "PHYSICAL_AREA", physical)
            self._upsert_clinical_note(patient, default_therapist, "EMOTIONAL_AREA", emotional)
            self._upsert_clinical_note(patient, default_therapist, "COGNITIVE_AREA", cognitive)
            self._upsert_clinical_note(patient, default_therapist, "SOCIAL_AREA", social)
            self._upsert_clinical_note(patient, default_therapist, "METHODS", methods)
            self._upsert_clinical_note(patient, default_therapist, "ADDITIONAL_NOTES", questionnaire)

            info_map[legacy_info_id] = {
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
                "first_name": first_name,
                "last_name": last_name,
                "ci": f"LEGACY-TUTOR-{legacy_info_id}",
                "celular": "",
                "status": "active",
                "visibility": "private",
                "is_active": True,
            },
        )
        tutor_user.set_password(secrets.token_urlsafe(16))
        tutor_user.save(update_fields=["password"])

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

    def _count_cycles_by_payment(self, rows):
        counts = defaultdict(int)
        for row in rows:
            if len(row) < 13:
                continue
            legacy_payment_id = self._to_int(row[1])
            counts[legacy_payment_id] += 1
        return counts

    def _import_payments(self, rows, info_map, payment_proofs, cycle_count_by_payment):
        payments_by_legacy = {}
        imported = 0

        for row in rows:
            if len(row) < 11:
                continue

            legacy_payment_id = self._to_int(row[0])
            legacy_info_id = self._to_int(row[1])
            info = info_map.get(legacy_info_id)
            if not info:
                continue

            patient = info["patient"]
            price_total = self._to_decimal(row[2], Decimal("0"))
            amount_paid = self._to_decimal(row[4], Decimal("0"))
            sessions_count = max(cycle_count_by_payment.get(legacy_payment_id, 0), 1)

            if sessions_count > 0:
                price_per_session = (price_total / Decimal(sessions_count)).quantize(Decimal("0.01"))
            else:
                price_per_session = price_total

            debt = price_total - amount_paid
            if debt <= 0:
                payment_status = Payment.PaymentStatus.COMPLETED
            elif amount_paid <= 0:
                payment_status = Payment.PaymentStatus.PENDING
            else:
                payment_status = Payment.PaymentStatus.PARTIAL

            payment_proof_url = payment_proofs.get(legacy_payment_id)
            payment_method = (
                Payment.PaymentMethod.QR if payment_proof_url else Payment.PaymentMethod.CASH
            )

            payment = Payment.objects.create(
                patient=patient,
                discount=None,
                sessions_count=sessions_count,
                price_per_session=price_per_session,
                amount_paid=amount_paid,
                payment_method=payment_method,
                payment_proof_url=payment_proof_url,
                payment_status=payment_status,
            )

            payments_by_legacy[legacy_payment_id] = payment
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
            raw_cycle = self._to_int(row[2])
            cycle_number = raw_cycle if raw_cycle is not None and raw_cycle > 0 else None
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

    def _import_intervention_plans(self, plan_rows, subplan_rows, info_map, created_by):
        plan_by_patient = {}
        step_by_legacy_plan_id = {}
        imported_steps = 0

        for row in plan_rows:
            if len(row) < 11:
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
                main_objective = self._clean_text(row[4]) or "Objetivo migrado desde legacy"
                plan = InterventionPlan.objects.create(
                    patient=patient,
                    created_by=created_by,
                    main_objective=main_objective,
                    start_date=timezone.now().date(),
                )
                plan_by_patient[patient.id] = plan

            step = PlanStep.objects.create(
                plan=plan,
                moment=self._map_plan_moment(row[3]),
                duration_minutes=self._to_int(row[8]),
                objective=self._clean_text(row[4]) or "Paso migrado",
                focus=self._clean_text(row[5]) or None,
                musical_resources=None,
                musical_emphasis=None,
                approach=self._clean_text(row[7]) or None,
                mlt_method=self._clean_text(row[6]) or None,
                order_index=order_index,
            )

            step_by_legacy_plan_id[legacy_plan_id] = step
            imported_steps += 1

        for row in subplan_rows:
            if len(row) < 6:
                continue

            legacy_plan_id = self._to_int(row[1])
            step = step_by_legacy_plan_id.get(legacy_plan_id)
            if not step:
                continue

            category = self._clean_text(row[2]).upper()
            value = self._clean_text(row[3])
            if not value:
                continue

            if "RECURSO" in category:
                step.musical_resources = self._append_text(step.musical_resources, value)
                step.save(update_fields=["musical_resources"])
            elif "ENFASIS" in category:
                step.musical_emphasis = self._append_text(step.musical_emphasis, value)
                step.save(update_fields=["musical_emphasis"])
            elif "MLT" in category:
                step.mlt_method = self._append_text(step.mlt_method, value)
                step.save(update_fields=["mlt_method"])
            elif "ENFOQUE" in category:
                step.approach = self._append_text(step.approach, value)
                step.save(update_fields=["approach"])
            else:
                step.focus = self._append_text(step.focus, value)
                step.save(update_fields=["focus"])

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
            subscale_name = self._clean_text(row[2])
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
            subscale_name = self._clean_text(row[3])
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

            category = self._clean_text(row[8]) or "ESCALA LEGACY"
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

            subscale_name = self._clean_text(row[4]) or f"ITEM-{self._to_int(row[0], 0)}"
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
            return PlanStep.Moment.INITIAL
        if value in {"relajacion", "relajacion.", "cierre"}:
            return PlanStep.Moment.CLOSURE
        return PlanStep.Moment.DEVELOPMENT

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

