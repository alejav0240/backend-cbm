"""Validation and merge helpers for therapist-reviewed DEMUCA drafts."""

from __future__ import annotations

import math
from numbers import Real
from typing import Any


DEMUCA_FIELDS: dict[str, tuple[str, ...]] = {
    "comportamientos_restrictivos": (
        "estereotipias", "agresividad", "desinteres", "pasividad",
        "aislamiento", "resistencia", "berrinche_crisis",
    ),
    "exploracion_vocal": (
        "vocalizaciones", "balbuceos", "silabas_canonicas",
        "imitacion_de_canciones", "creacion_vocal", "comunicacion_verbal",
    ),
    "interaccion_social_cognitiva": (
        "contacto_visual", "interaccion_con_otros_objetos",
        "interaccion_con_instrumentos_musicales",
        "interaccion_con_el_educador_musicoterapeuta",
        "interaccion_con_sus_padres", "interaccion_con_sus_pares",
        "atencion", "imitacion",
    ),
    "movimiento_corporal": (
        "andar", "correr", "parar", "gesticular", "danzar",
        "movimiento_en_su_lugar", "saltar",
    ),
    "exploracion_sonora": (
        "sonido_silencio", "timbre", "planos_de_altura",
        "movimiento_sonoro", "contrastes_de_intensidad",
    ),
    "exploracion_ritmica": (
        "repeticion_de_ideas_ritmicas_melodicas", "sensacion_de_conclusion",
        "pulso_interno", "regulacion_temporal", "ritmo_real", "apoyo",
        "contrastes_de_tempo",
    ),
}


def merge_demuca_data(
    current: dict[str, Any] | None,
    incoming: dict[str, Any],
    *,
    session_id: str,
) -> dict[str, Any]:
    """Merge and validate therapist edits while preserving the fixed DEMUCA schema."""
    if not isinstance(incoming, dict):
        raise ValueError("demuca_data_must_be_object")
    if "sesion_id" in incoming and incoming["sesion_id"] != session_id:
        raise ValueError("demuca_session_id_mismatch")

    current = current if isinstance(current, dict) else {}
    normalized: dict[str, Any] = {"sesion_id": session_id}
    for category, fields in DEMUCA_FIELDS.items():
        source = current.get(category, {})
        patch = incoming.get(category, {})
        if not isinstance(source, dict) or not isinstance(patch, dict):
            raise ValueError(f"demuca_category_must_be_object:{category}")
        unknown = set(patch).difference(fields)
        if unknown:
            raise ValueError(f"demuca_unknown_field:{category}:{sorted(unknown)[0]}")
        merged = {field: source.get(field, 0) for field in fields}
        merged.update(patch)
        for field in fields:
            value = merged[field]
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)):
                raise ValueError(f"demuca_value_must_be_finite_number:{category}:{field}")
            if float(value) < 0:
                raise ValueError(f"demuca_value_must_be_non_negative:{category}:{field}")
            merged[field] = int(value) if float(value).is_integer() else float(value)
        normalized[category] = merged
    return normalized
