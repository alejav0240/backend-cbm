
from datetime import datetime, time
from typing import Dict, List
import sys

from django.utils import timezone
from django.db import transaction

from therapeutic_sessions.models import Session
from users.models import User
from finance.models import Payment
from evaluations.models import Scale, ScaleValue, ScaleEvaluation, ScaleEvaluationValueResponse
from .base_importer import BaseImporter


class SessionImporter(BaseImporter):
    """
    Clase dedicada a la importación de sesiones y sus evaluaciones clínicas (ERI/CIM).
    """

    def __init__(self, logger=None, dry_run=False):
        super().__init__(logger, dry_run)
        self.stats = {'sessions': 0, 'evaluations': 0}
        self._cache_scale_values = {} # (scale_id, normalized_text) -> ScaleValue

    def import_sessions(self, rows: List[List[str]], payments_by_legacy: Dict[int, Payment], therapist: User):
        """
        Importa sesiones y vincula evaluaciones ERI/CIM.
        """
        self.stats = {'sessions': 0, 'evaluations': 0}
        self._cache_scale_values = self._load_scale_values()
        
        total_rows = len(rows)
        self.logger(f"📥 Iniciando importación de {total_rows} sesiones...")

        skipped_no_payment = []
        skipped_short_row = []

        for index, row in enumerate(rows, 1):
            if len(row) < 12:
                skipped_short_row.append(index)
                continue

            try:
                result = self._process_row(row, payments_by_legacy, therapist)
                if result == 'no_payment':
                    legacy_payment_id = self._to_int(row[1])
                    skipped_no_payment.append((index, legacy_payment_id, row))
            except Exception as e:
                self.logger(f"❌ Error procesando sesión en fila {index}: {str(e)}")
                self.logger(f"❌ Error procesando en fila {index}: {str(row)}")
                sys.exit(1)

        # Reporte de descartadas
        if skipped_short_row:
            self.logger(f"⚠️  Filas descartadas por columnas insuficientes (<14): {len(skipped_short_row)} → filas {skipped_short_row}")
        if skipped_no_payment:
            self.logger(f"⚠️  Sesiones descartadas por payment no encontrado: {len(skipped_no_payment)}")
            for fila, pid, r in skipped_no_payment:
                self.logger(f"    fila {fila}: id_pago={pid} | ciclo_id={r[0]} | nrociclo={r[2]} | estado={r[4]}")

        total_discarded = len(skipped_short_row) + len(skipped_no_payment)
        self.logger(f"📊 Resumen: {total_rows} recibidas | {self.stats['sessions']} importadas | {total_discarded} descartadas")
        self.logger(f"✅ Sesiones migradas: {self.stats['sessions']}")
        self.logger(f"✅ Evaluaciones ERI/CIM vinculadas: {self.stats['evaluations']}")

    def _process_row(self, row, payments_by_legacy, therapist):
        # Indices: 0:ci.id, 1:ci.id_pago, 2:nrociclo, 3:sesion, 4:estadosesion, 5:ci.fecha, 6:estadopago, 7:eri, 8:cim, 9:ejecucion, 10:apuntes, 11:ci.created_at, 12:ci.updated_at
        legacy_id = self._to_int(row[0])
        legacy_payment_id = self._to_int(row[1])
        payment = payments_by_legacy.get(legacy_payment_id)
        
        if not payment:
            return 'no_payment'

        raw_date = self._to_date(row[5])
        session_datetime = timezone.make_aware(datetime.combine(raw_date, time(12, 0))) if raw_date else None
        session_number = self._to_int(row[3], 0)
        raw_cycle = self._to_int(row[2])
        cycle_number = raw_cycle if raw_cycle is not None and raw_cycle > 0 else None
        session_status = self._map_session_status(row[4])
        payment_status = self._map_session_payment_status(row[6])
        created_at = self._to_datetime(row[11]) if len(row) > 11 else timezone.now()

        eri_text = self._clean_text(row[7])
        cim_text = self._clean_text(row[8])
        ejecucion = self._clean_text(row[9])
        apuntes = self._clean_text(row[10])
        
        notes_parts = [p for p in [ejecucion, apuntes] if p]
        notes = "\n".join(notes_parts) if notes_parts else None

        if self.dry_run:
            session = Session(
                patient=payment.patient,
                therapist=therapist,
                session_date=session_datetime,
                session_status=session_status,
                payment_status=payment_status,
                notes=notes,
                created_at=created_at
            )
            # En dry-run simulamos la creación de evaluaciones
            if eri_text: self.stats['evaluations'] += 1
            if cim_text: self.stats['evaluations'] += 1
        else:
            session = Session.objects.create(
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
            # Forzar fecha de creación
            Session.objects.filter(pk=session.pk).update(created_at=created_at)
            
            # Procesar ERI (Scale 2) y CIM (Scale 3)
            self._create_evaluation_response(session, 2, eri_text,created_at)
            self._create_evaluation_response(session, 3, cim_text,created_at)
            
        self.stats['sessions'] += 1

    def _create_evaluation_response(self, session, scale_id, text,created_at):
        if not text:
            return
            
        # Buscar el valor de escala que coincida con el texto
        norm_text = self._normalize_name(text)
        scale_value = self._cache_scale_values.get((scale_id, norm_text))
        
        if not scale_value:
            # Intento de búsqueda parcial si no hay coincidencia exacta
            for (sid, t), sv in self._cache_scale_values.items():
                if sid == scale_id and (norm_text in t or t in norm_text):
                    scale_value = sv
                    break
        
        if scale_value:
            evaluation = ScaleEvaluation.objects.create(
                scale_id=scale_id,
                patient=session.patient,
                evaluator=session.therapist,
                session=session,
                evaluated_at=created_at,
            )
            ScaleEvaluationValueResponse.objects.create(
                evaluation=evaluation,
                scale_value=scale_value
            )
            self.stats['evaluations'] += 1

    def _load_scale_values(self):
        """Pre-carga los valores de escala para ERI y CIM."""
        cache = {}
        for sv in ScaleValue.objects.filter(scale_id__in=[2, 3]):
            # El label suele ser "1: TEXTO", queremos normalizar el TEXTO
            parts = sv.label.split(":", 1)
            text = parts[1] if len(parts) > 1 else parts[0]
            cache[(sv.scale_id, self._normalize_name(text))] = sv
        return cache

    def _map_session_status(self, legacy_status):
        value = self._clean_text(legacy_status).upper()
        if "PENDIENTE" in value:
            return Session.SessionStatus.AGENDADA
        
        mapping = {
            "REALIZADO":    Session.SessionStatus.COMPLETADA,
            "CONFIRMADO":   Session.SessionStatus.CONFIRMADA,
            "REPROGRAMADO": Session.SessionStatus.REPROGRAMA,
            "CANCELADO":    Session.SessionStatus.CANCELADA,
        }
        return mapping.get(value, Session.SessionStatus.COMPLETADA)

    def _map_session_payment_status(self, legacy_payment_status):
        value = self._clean_text(legacy_payment_status).upper()
        if value == "PAGADO":
            return Session.PaymentStatus.PAID
        if value == "PRESTADO":
            return Session.PaymentStatus.EXEMPT
        return Session.PaymentStatus.PENDING
