from __future__ import annotations

import secrets
from datetime import datetime
from decimal import Decimal

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

from .importers.user_importer import UserImporter
from .importers.patient_importer import PatientImporter
from .importers.payment_importer import PaymentImporter
from .importers.session_importer import SessionImporter
from .importers.intervention_plan_importer import InterventionPlanImporter
from .importers.scale_importer import ScaleImporter


class Command(BaseCommand):
    help = "ETL desde base de datos legacy Laravel (MariaDB) hacia modelos Django refactorizado."

    def add_arguments(self, parser):
        parser.add_argument("--host", default="cpanel.musicoterapiabolivia.com")
        parser.add_argument("--user", default="hmusicot")
        parser.add_argument("--password", default="")
        parser.add_argument("--database", default="hmusicot_musicoterapiadb")
        parser.add_argument("--port", type=int, default=3306)
        parser.add_argument("--truncate", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        config = {
            "host": options["host"],
            "user": options["user"],
            "password": options["password"],
            "database": options["database"],
            "port": options["port"],
            "connect_timeout": 30,
        }

        self.stdout.write(self.style.NOTICE(f"Conectando a {config['host']}..."))
        try:
            conn_remote = mysql.connector.connect(**config)
        except mysql.connector.Error as err:
            raise CommandError(f"Error de conexión: {err}")

        try:
            datasets = self._fetch_all_datasets(conn_remote)
        finally:
            conn_remote.close()

        dry_run = options["dry_run"]
        self.stdout.write(self.style.NOTICE("Iniciando ETL legacy (Refactorizado)..."))

        with transaction.atomic():
            if options["truncate"]:
                self._truncate_imported_data()
                # Re-seed static scales after truncation
                from django.core.management import call_command
                self.stdout.write(self.style.NOTICE("Re-seeding scales..."))
                call_command('seed_scales')

            therapist = self._ensure_default_therapist()
            
            # Inicializar importadores
            user_importer = UserImporter(logger=self.stdout.write, dry_run=dry_run)
            patient_importer = PatientImporter(logger=self.stdout.write, dry_run=dry_run)
            payment_importer = PaymentImporter(logger=self.stdout.write, dry_run=dry_run)
            session_importer = SessionImporter(logger=self.stdout.write, dry_run=dry_run)
            plan_importer = InterventionPlanImporter(logger=self.stdout.write, dry_run=dry_run)
            scale_importer = ScaleImporter(logger=self.stdout.write, dry_run=dry_run)

            # Ejecutar importación en orden de dependencias
            users_by_name = user_importer.import_users(datasets["usuarios"])
            
            patients_by_legacy_client, info_map = patient_importer.import_patients(
                datasets["clientes"], 
                users_by_name, 
                therapist
            )
            
            payment_proofs = payment_importer.extract_payment_proofs(datasets["archivospagos"])
            payments_by_legacy = payment_importer.import_payments(
                datasets["pagos"], 
                info_map, 
                payment_proofs
            )
            
            session_importer.import_sessions(datasets["ciclos"], payments_by_legacy, therapist)
            
            plan_importer.import_intervention_plans(datasets["plandeintervencions"], info_map, therapist)
            
            scale_importer.import_scales_and_evaluations(
                datasets["matrizescalas"],
                datasets["submatrizescalas"],
                datasets["demucas"],
                info_map,
                therapist
            )

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("Rollback realizado (dry-run)."))

        self.stdout.write(self.style.SUCCESS("ETL completado exitosamente."))

    def _fetch_all_datasets(self, conn):
        tables = [
            "usuarios", "clientes", "pagos", "archivospagos", 
            "ciclos", "plandeintervencions", "matrizescalas", 
            "submatrizescalas", "demucas"
        ]
        datasets = {}
        for table in tables:
            datasets[table] = self._query_table(conn, table)
        return datasets

    def _query_table(self, conn, table_name):
        cursor = conn.cursor()
        
        # Mapeo explícito de queries para asegurar el orden de las columnas que esperan los importadores
        queries = {
            "usuarios": """
                SELECT id, nombres, apellidos, usuario, celulartrabajo, celular, carnet, 
                       visibilidad, estado, foto, created_at, updated_at 
                FROM usuarios
            """,
            "clientes": """
                SELECT cli.id, cli.nombres, cli.apellidos, cli.carnet, cli.fechnac, cli.foto,
                       inf.notas, inf.diagnostico, inf.residenciaactual, 
                       COALESCE(inf.tutor, CONCAT('TUTOR ', cli.nombres)) AS tutor,
                       cli.usuario, cli.celular, inf.objgenerales, inf.social, 
                       inf.cognitivo, inf.fisico, inf.emocional, inf.metodosausar, inf.cuestionario,
                       inf.id AS info_id, cli.created_at
                FROM clientes cli
                LEFT JOIN infoclientes inf ON cli.id = inf.id_cliente
            """,
            "pagos": """
                SELECT id, id_infocliente, precio, pagado, tipo, descuento 
                FROM pagos
            """,
            "archivospagos": """
                SELECT id, id_pago, monto, fechapago, created_at, file, updated_at, estadopago, created_at, updated_at 
                FROM archivospagos
            """,
            "ciclos": """
                SELECT c.id, inc.id, ci.id, id_pago, nrociclo, sesion, estadosesion, ci.fecha,
                       estadopago, eri, cim, ejecucion, apuntes, ci.created_at, ci.updated_at
                FROM clientes c
                INNER JOIN infoclientes inc ON c.id = inc.id_cliente
                INNER JOIN pagos pg ON inc.id = pg.id_infocliente
                INNER JOIN ciclos ci ON pg.id = ci.id_pago
            """,
            "plandeintervencions": """
                SELECT pi.id, pi.orden, inf.id, pi.momento, pi.objetivo, pi.foco, 
                       pi.mlt, pi.enfoque, pi.duracion, inf.objgenerales,
                       (SELECT GROUP_CONCAT(sp.nombre SEPARATOR ' | ') FROM subplandeintervencions sp 
                        WHERE sp.categoria = 'RECURSOS MUSICALES' AND sp.id_plandeintervencion = pi.id) AS musical_resources,
                       (SELECT GROUP_CONCAT(sp.nombre SEPARATOR ' | ') FROM subplandeintervencions sp 
                        WHERE sp.categoria = 'ENFASIS MUSICAL' AND sp.id_plandeintervencion = pi.id) AS musical_emphasis,
                       pi.created_at, pi.updated_at
                FROM plandeintervencions pi
                INNER JOIN infoclientes inf ON pi.id_infocliente = inf.id
            """,
            "matrizescalas": """
                SELECT id, categoria, nombrematriz, created_at, updated_at 
                FROM matrizescalas
                WHERE categoria = 'RECURSOS MUSICALES'
            """,
            "submatrizescalas": """
                SELECT id, id_matrizescala, tipo, nombresubmatriz, created_at, updated_at 
                FROM submatrizescalas
            """,
            "demucas": """
                SELECT id, id_infocliente, evaluacion, palabra, escala,
                       CASE escala
                           WHEN 'NADA'  THEN 0
                           WHEN 'POCO'  THEN 1
                           WHEN 'MUCHO' THEN 2
                           ELSE 0
                       END AS valor,
                       fecha, categoria, created_at, updated_at
                FROM demucas
            """
        }

        query = queries.get(table_name, f"SELECT * FROM {table_name}")

        cursor.execute(query)
        rows = cursor.fetchall()
        
        # Convertir a listas de strings para los importadores
        result = []
        for row in rows:
            result.append([str(val) if val is not None else "" for val in row])
            
        self.stdout.write(self.style.SUCCESS(f"Tabla '{table_name}': {len(result)} registros."))
        cursor.close()
        return result

    def _truncate_imported_data(self):
        self.stdout.write(self.style.WARNING("Limpiando datos previos..."))
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
        therapist = User.objects.filter(id=1).first() or User.objects.filter(is_superuser=True).first()
        if not therapist:
            therapist, _ = User.objects.get_or_create(
                username="legacy_admin",
                defaults={"first_name": "Legacy", "last_name": "Admin", "is_staff": True, "is_superuser": True}
            )
            therapist.set_password(secrets.token_urlsafe(16))
            therapist.save()
        return therapist
