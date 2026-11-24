"""Persist provisional DEMUCA worker output in the existing evaluation tables."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from evaluations.models import (
    Scale,
    ScaleEvaluation,
    ScaleEvaluationSubscaleResponse,
    Subscale,
)


WORKER_TO_SUBSCALE = {
    "comportamientos_restrictivos.estereotipias": "Estereotipias",
    "comportamientos_restrictivos.agresividad": "Agresividad",
    "comportamientos_restrictivos.desinteres": "Desinterés",
    "comportamientos_restrictivos.pasividad": "Pasividad",
    "comportamientos_restrictivos.resistencia": "Resistencia",
    "comportamientos_restrictivos.aislamiento": "Reclusión / Aislamiento",
    "comportamientos_restrictivos.berrinche_crisis": "Berrinche",
    "exploracion_vocal.vocalizaciones": "Vocalizaciones",
    "exploracion_vocal.balbuceos": "Balbuceos",
    "exploracion_vocal.silabas_canonicas": "Sílabas Canónicas",
    "exploracion_vocal.imitacion_de_canciones": "Imitación de Canciones",
    "exploracion_vocal.creacion_vocal": "Creación Vocal",
    "exploracion_vocal.comunicacion_verbal": "Comunicación Verbal",
    "interaccion_social_cognitiva.contacto_visual": "Contacto Visual",
    "interaccion_social_cognitiva.interaccion_con_otros_objetos": "Interacción con Otros Objetos",
    "interaccion_social_cognitiva.interaccion_con_instrumentos_musicales": "Interacción con Instrumentos",
    "interaccion_social_cognitiva.interaccion_con_el_educador_musicoterapeuta": "Interacción con Educador / Musicoterapeuta",
    "interaccion_social_cognitiva.interaccion_con_sus_padres": "Interacción con Padres",
    "interaccion_social_cognitiva.interaccion_con_sus_pares": "Interacción con Pares",
    "interaccion_social_cognitiva.atencion": "Atención",
    "interaccion_social_cognitiva.imitacion": "Imitación",
    "exploracion_ritmica.pulso_interno": "Pulso Interno",
    "exploracion_ritmica.regulacion_temporal": "Regulación Temporal",
    "exploracion_ritmica.apoyo": "Apoyo Rítmico",
    "exploracion_ritmica.ritmo_real": "Ritmo Real",
    "exploracion_ritmica.contrastes_de_tempo": "Contrastes de Tempo",
    "exploracion_sonora.sonido_silencio": "Sonido Silencio",
    "exploracion_sonora.timbre": "Timbre",
    "exploracion_sonora.planos_de_altura": "Planos de Altura",
    "exploracion_sonora.movimiento_sonoro": "Movimiento Sonoro",
    "exploracion_sonora.contrastes_de_intensidad": "Contrastes de Intensidad",
    "exploracion_sonora.repeticion_de_ideas_ritmicas_melodicas": "Repetición de Ideas Rítmicas o Melódicas",
    "exploracion_ritmica.repeticion_de_ideas_ritmicas_melodicas": "Repetición de Ideas Rítmicas o Melódicas",
    "exploracion_sonora.sensacion_de_conclusion": "Sentido de Conclusión",
    "exploracion_ritmica.sensacion_de_conclusion": "Sentido de Conclusión",
    "movimiento_corporal.andar": "Andar",
    "movimiento_corporal.correr": "Correr",
    "movimiento_corporal.parar": "Parar",
    "movimiento_corporal.danzar": "Bailar",
    "movimiento_corporal.saltar": "Saltar",
    "movimiento_corporal.gesticular": "Gesticular",
    "movimiento_corporal.movimiento_en_su_lugar": "Moverse en el Sitio",
}


def _worker_scores(result: dict[str, Any]) -> dict[str, int]:
    demuca = result.get("demuca")
    if not isinstance(demuca, dict):
        return {}

    scores: dict[str, int] = {}
    for domain, values in demuca.items():
        if not isinstance(values, dict):
            continue
        for item, score in values.items():
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                continue
            subscale_name = WORKER_TO_SUBSCALE.get(f"{domain}.{item}")
            if subscale_name:
                scores[subscale_name] = max(0, min(2, int(score)))
    return scores


@transaction.atomic
def persist_demuca_evaluation(processing_run: Any) -> ScaleEvaluation | None:
    """Upsert one provisional DEMUCA evaluation for a completed processing run."""

    session = processing_run.session
    patient = session.patient
    result = processing_run.result_json
    if (
        not patient
        or not isinstance(result, dict)
        or not isinstance(result.get("demuca"), dict)
    ):
        return None

    scale = Scale.objects.filter(name__iexact="Escala DEMUCA").first()
    if not scale:
        raise ValueError("demuca_scale_not_seeded")

    evaluator = processing_run.requested_by or session.therapist
    evaluation = (
        ScaleEvaluation.objects.filter(session=session, scale=scale)
        .order_by("-evaluated_at", "-id")
        .first()
    )
    if evaluation is None:
        evaluation = ScaleEvaluation.objects.create(
            patient=patient,
            evaluator=evaluator,
            scale=scale,
            session=session,
        )
    else:
        # A worker rerun must never replace a therapist's existing evaluation.
        # The raw worker result remains auditable in ProcessingRun.result_json.
        return evaluation

    scores = _worker_scores(result)
    subscales = {
        subscale.name: subscale
        for subscale in Subscale.objects.filter(scale=scale)
    }
    for name, subscale in subscales.items():
        ScaleEvaluationSubscaleResponse.objects.update_or_create(
            evaluation=evaluation,
            subscale=subscale,
            defaults={"score": scores.get(name, 0)},
        )

    return evaluation
