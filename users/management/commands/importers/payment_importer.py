
from decimal import Decimal
from typing import Dict, List

from finance.models import Discount, Payment
from .base_importer import BaseImporter


class PaymentImporter(BaseImporter):
    """
    Clase dedicada a la importación de pagos.
    """

    def __init__(self, logger=None, dry_run=False):
        super().__init__(logger, dry_run)
        self.payments_by_legacy = {}
        self.stats = {'payments': 0}

    def import_payments(self, rows: List[List[str]], info_map: Dict[int, dict], payment_proofs: Dict[int, str]) -> Dict[int, Payment]:
        """
        Importa pagos.
        """
        self.payments_by_legacy = {}
        self.stats = {'payments': 0}
        
        # Mapeo de descuentos: 50 → id 1, 25 → id 2
        discount_mapping = {
            "50": 1,
            "25": 2,
        }

        total_rows = len(rows)
        self.logger(f"📥 Iniciando importación de {total_rows} pagos...")

        skipped_no_info = []

        for index, row in enumerate(rows, 1):
            if len(row) < 5:
                continue

            try:
                result = self._process_row(row, info_map, payment_proofs, discount_mapping)
                if result == 'no_info':
                    legacy_payment_id = self._to_int(row[0])
                    patient_legacy_info_id = self._to_int(row[1])
                    skipped_no_info.append((index, legacy_payment_id, patient_legacy_info_id))
            except Exception as e:
                self.logger(f"❌ Error procesando pago en fila {index}: {str(e)}")

        if skipped_no_info:
            self.logger(f"⚠️  Pagos descartados por info_map no encontrado: {len(skipped_no_info)}")
            for fila, pid, iid in skipped_no_info:
                self.logger(f"    fila {fila}: legacy_payment_id={pid} | id_infocliente={iid} (sin paciente asociado)")

        self.logger(f"✅ Pagos migrados: {self.stats['payments']}")
        return self.payments_by_legacy

    def _process_row(self, row, info_map, payment_proofs, discount_mapping):
        legacy_payment_id = self._to_int(row[0])
        patient_legacy_info_id = self._to_int(row[1])
        price_per_session = self._to_decimal(row[2], Decimal("0"))
        amount_paid = self._to_decimal(row[3], Decimal("0"))
        payment_type_raw = self._clean_text(row[4]).lower()
        descuento_raw = self._clean_text(row[5])

        info = info_map.get(patient_legacy_info_id)
        if not info:
            return 'no_info'
        
        patient = info["patient"]

        # Mapear tipo
        if "mensual" in payment_type_raw:
            payment_type = Payment.PaymentType.THERAPY_MONTHLY
            sessions_count = 1
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

        payment_proof_url = payment_proofs.get(legacy_payment_id)
        payment_method = (
            Payment.PaymentMethod.QR if payment_proof_url else Payment.PaymentMethod.CASH
        )

        payment_status = Payment.PaymentStatus.COMPLETED

        if self.dry_run:
            payment = Payment(patient=patient, amount_paid=amount_paid)
        else:
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

        self.payments_by_legacy[legacy_payment_id] = payment
        self.stats['payments'] += 1

    def extract_payment_proofs(self, rows: List[List[str]]) -> Dict[int, str]:
        """
        Extrae los comprobantes de pago.
        """
        proof_by_payment_id = {}
        for row in rows:
            if len(row) < 10:
                continue
            legacy_payment_id = self._to_int(row[1])
            file_path = self._clean_text(row[5])
            if file_path:
                proof_by_payment_id[legacy_payment_id] = file_path
        return proof_by_payment_id
