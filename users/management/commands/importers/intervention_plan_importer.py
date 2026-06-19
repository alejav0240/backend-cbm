
from typing import Dict, List

from django.utils import timezone

from clinical.models import InterventionPlan, PlanStep
from users.models import User
from .base_importer import BaseImporter


class InterventionPlanImporter(BaseImporter):
    """
    Clase dedicada a la importación de planes de intervención.
    """

    def __init__(self, logger=None, dry_run=False):
        super().__init__(logger, dry_run)
        self.stats = {'steps': 0}

    def import_intervention_plans(self, plan_rows: List[List[str]], info_map: Dict[int, dict], created_by: User):
        """
        Importa planes de intervención y sus pasos.
        """
        self.stats = {'steps': 0}
        plan_by_patient = {}
        total_rows = len(plan_rows)
        self.logger(f"📥 Iniciando importación de {total_rows} pasos de planes...")

        for index, row in enumerate(plan_rows, 1):
            if len(row) < 14:
                continue

            try:
                self._process_row(row, info_map, created_by, plan_by_patient)
            except Exception as e:
                self.logger(f"❌ Error procesando paso de plan en fila {index}: {str(e)}")

        self.logger(f"✅ Pasos de planes migrados: {self.stats['steps']}")

    def _process_row(self, row, info_map, created_by, plan_by_patient):
        legacy_plan_id = self._to_int(row[0])
        order_index = self._to_int(row[1], 0)
        legacy_info_id = self._to_int(row[2])
        info = info_map.get(legacy_info_id)
        if not info:
            return

        patient = info["patient"]
        plan = plan_by_patient.get(patient.id)
        if not plan:
            main_objective = self._limit_text(self._clean_text(row[9]) or "Objetivo migrado desde legacy", 500)
            if self.dry_run:
                plan = InterventionPlan(patient=patient, main_objective=main_objective)
            else:
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

        if not self.dry_run:
            PlanStep.objects.create(
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
        self.stats['steps'] += 1

    def _map_plan_moment(self, legacy_moment):
        value = self._clean_text(legacy_moment).lower()
        if value in {"bienvenida", "inicio", "inicial"}:
            return PlanStep.Moment.BIENVENIDA
        if value in {"relajacion", "relajacion.", "despedida", "cierre"}:
            return PlanStep.Moment.RELAJACION
        
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
        return moment_mapping.get(value, PlanStep.Moment.BIENVENIDA)
