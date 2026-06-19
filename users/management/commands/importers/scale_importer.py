
from typing import Dict, List

from django.utils import timezone

from evaluations.models import Scale, ScaleEvaluation, ScaleEvaluationSubscaleResponse, Subscale
from therapeutic_sessions.models import DigitalResource
from users.models import User
from .base_importer import BaseImporter


class ScaleImporter(BaseImporter):
    """
    Clase dedicada a la importación de escalas y evaluaciones, incluyendo DEMUCA.
    También importa recursos musicales desde la matriz de escalas.
    """

    def __init__(self, logger=None, dry_run=False):
        super().__init__(logger, dry_run)
        self.stats = {'responses': 0, 'scales': 0, 'evaluations': 0, 'resources': 0}
        self._subscale_cache = {} # (scale_id, normalized_name) -> Subscale

    def import_scales_and_evaluations(
        self,
        matrix_rows: List[List[str]],
        submatrix_rows: List[List[str]],
        demucas_rows: List[List[str]],
        info_map: Dict[int, dict],
        evaluator: User,
    ):
        """
        Importa escalas, subescalas y respuestas de evaluación.
        También importa recursos digitales.
        """
        self.stats = {'responses': 0, 'scales': 0, 'evaluations': 0, 'resources': 0}
        self._subscale_cache = self._load_subscale_cache()

        # 1. Procesar matriz como recursos digitales (RECURSOS MUSICALES)
        self.logger("📥 Procesando matriz de escalas como Recursos Digitales...")
        for row in matrix_rows:
            if len(row) < 3:
                continue
            self._process_resource_row(row)

        # 2. Procesar DEMUCA (Escala ID 1)
        eval_cache = {}
        self.logger(f"📥 Procesando {len(demucas_rows)} evaluaciones DEMUCA...")
        
        # Asegurar que la escala DEMUCA existe
        demuca_scale = Scale.objects.filter(id=1).first()
        
        for index, row in enumerate(demucas_rows, 1):
            if len(row) < 8:
                continue

            try:
                self._process_demuca_row(row, info_map, evaluator, demuca_scale, eval_cache)
            except Exception as e:
                self.logger(f"❌ Error procesando DEMUCA en fila {index}: {str(e)}")

        self.logger(f"✅ Recursos digitales migrados: {self.stats['resources']}")
        self.logger(f"✅ Respuestas de evaluación migradas: {self.stats['responses']}")

    def _process_resource_row(self, row):
        # Indices: 0:id, 1:categoria, 2:nombrematriz, 3:created_at, 4:updated_at
        title = self._clean_text(row[2])
        category = self._clean_text(row[1])
        
        if not title:
            return

        if self.dry_run:
            self.stats['resources'] += 1
        else:
            # Evitar duplicados por título
            resource, created = DigitalResource.objects.get_or_create(
                title=title,
                defaults={
                    "type": DigitalResource.ResourceType.AUDIO, # Default por ser recursos musicales
                    "category": category,
                    "url": "http://legacy.com/placeholder" # Placeholder
                }
            )
            if created:
                self.stats['resources'] += 1

    def _process_demuca_row(self, row, info_map, evaluator, demuca_scale, eval_cache):
        # Indices: 0:id, 1:id_infocliente, 2:evaluacion, 3:palabra, 4:escala, 5:valor, 6:fecha, 7:categoria, 8:created_at, 9:updated_at
        legacy_info_id = self._to_int(row[1])
        info = info_map.get(legacy_info_id)
        if not info:
            return

        # Si no hay escala DEMUCA (id=1), creamos una dinámica basada en la categoría legacy
        if not demuca_scale:
            category_name = self._limit_text(self._clean_text(row[7]) or "DEMUCA", 255)
            scale = self._get_or_create_dynamic_scale(category_name)
        else:
            scale = demuca_scale

        subscale_name = self._clean_text(row[3])
        score = self._to_int(row[5], 0)
        eval_name = self._clean_text(row[2])
        eval_date = self._to_date(row[6]) or timezone.now().date()
        created_at = self._to_datetime(row[8]) if len(row) > 8 else timezone.now()

        # Buscar subescala (flexible)
        subscale = self._find_subscale(scale, subscale_name)
        if not subscale:
            return

        # Cache de evaluaciones para agrupar respuestas por (paciente, escala, nombre_eval, fecha)
        cache_key = (legacy_info_id, scale.id, eval_name, eval_date.isoformat())
        evaluation = eval_cache.get(cache_key)
        
        if not evaluation and not self.dry_run:
            evaluation = ScaleEvaluation.objects.create(
                scale=scale,
                patient=info["patient"],
                evaluator=evaluator,
                session=None,
            )
            # Forzar fecha de creación
            ScaleEvaluation.objects.filter(pk=evaluation.pk).update(evaluated_at=created_at)
            eval_cache[cache_key] = evaluation

        if not self.dry_run and evaluation:
            ScaleEvaluationSubscaleResponse.objects.update_or_create(
                evaluation=evaluation,
                subscale=subscale,
                defaults={"score": score},
            )
        self.stats['responses'] += 1

    def _find_subscale(self, scale, name):
        if self.dry_run: return Subscale(name=name)
        
        norm_name = self._normalize_name(name)
        
        # Intento 1: Cache exacto
        sub = self._subscale_cache.get((scale.id, norm_name))
        if sub: return sub
        
        # Intento 2: Búsqueda parcial o fuzzy básica
        for (sid, cached_norm), subscale in self._subscale_cache.items():
            if sid == scale.id:
                if norm_name in cached_norm or cached_norm in norm_name:
                    return subscale
                    
        # Intento 3: Crear si no existe en la escala dinámica
        if scale.id != 1:
            sub, _ = Subscale.objects.get_or_create(
                scale=scale,
                name=name[:255],
                defaults={"max_value": 2}
            )
            self._subscale_cache[(scale.id, norm_name)] = sub
            return sub
            
        return None

    def _get_or_create_dynamic_scale(self, name):
        if self.dry_run: return Scale(name=name)
        scale, _ = Scale.objects.get_or_create(
            name=name,
            defaults={"scale_type": Scale.ScaleType.SUBSCALE}
        )
        return scale

    def _load_subscale_cache(self):
        cache = {}
        for sub in Subscale.objects.all():
            cache[(sub.scale_id, self._normalize_name(sub.name))] = sub
        return cache
