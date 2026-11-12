"""Validate session fragment manifests against one session-relative clock."""

from __future__ import annotations

import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


SCHEMA_VERSION = "1.0"
CLOCK = "session_elapsed_seconds"
TIMELINE_POLICIES = {"contiguous", "preserve_gaps"}


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _resolve_source_path(
    relative_path: Any,
    session_dir: Path,
    field_path: str,
    errors: list[dict[str, str]],
    check_files: bool,
) -> None:
    if not isinstance(relative_path, str) or not relative_path.strip():
        errors.append(_issue("invalid_source_path", field_path, "expected a non-empty relative path"))
        return
    posix_path = PurePosixPath(relative_path)
    windows_path = PureWindowsPath(relative_path)
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or ".." in posix_path.parts
        or "\\" in relative_path
    ):
        errors.append(_issue("unsafe_source_path", field_path, "path must stay inside the session directory"))
        return
    if check_files:
        root = session_dir.resolve()
        resolved = (root / Path(*posix_path.parts)).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            errors.append(_issue("unsafe_source_path", field_path, "path resolves outside the session directory"))
            return
        if not resolved.is_file():
            errors.append(_issue("source_file_missing", field_path, f"file does not exist: {relative_path}"))


def _validate_participant(participant: Any, path: str, ids: set[str], errors: list[dict[str, str]]) -> None:
    if not isinstance(participant, dict):
        errors.append(_issue("invalid_participant", path, "participant must be an object"))
        return
    for key in sorted(participant.keys() - {"id", "role"}):
        errors.append(_issue("unknown_field", f"{path}.{key}", f"field '{key}' is not in the participant schema"))
    for key in sorted({"id", "role"} - participant.keys()):
        errors.append(_issue("required_field_missing", f"{path}.{key}", f"required field '{key}' is missing"))
    participant_id = participant.get("id")
    role = participant.get("role")
    if not isinstance(participant_id, str) or not participant_id.strip():
        errors.append(_issue("invalid_participant_id", f"{path}.id", "id must be a non-empty string"))
    elif participant_id in ids:
        errors.append(_issue("duplicate_participant_id", f"{path}.id", f"duplicate id '{participant_id}'"))
    else:
        ids.add(participant_id)
    if not isinstance(role, str) or role not in {"PATIENT", "THERAPIST", "UNKNOWN"}:
        errors.append(_issue("invalid_participant_role", f"{path}.role", "role must be PATIENT, THERAPIST, or UNKNOWN"))


def _validate_fragment_schema(fragment: dict[str, Any], path: str, errors: list[dict[str, str]]) -> None:
    allowed = {"fragment_id", "order", "global_start_seconds", "duration_seconds", "video_path", "audio_path"}
    for key in sorted(fragment.keys() - allowed):
        errors.append(_issue("unknown_field", f"{path}.{key}", f"field '{key}' is not in the fragment schema"))
    for key in sorted((allowed - {"audio_path"}) - fragment.keys()):
        errors.append(_issue("required_field_missing", f"{path}.{key}", f"field '{key}' is not in the fragment schema"))


def _validate_fragment_identity(fragment_id, order, path, ids, orders, errors) -> bool:
    if not isinstance(fragment_id, str) or not fragment_id.strip():
        errors.append(_issue("invalid_fragment_id", f"{path}.fragment_id", "fragment_id must be a non-empty string"))
    elif fragment_id in ids:
        errors.append(_issue("duplicate_fragment_id", f"{path}.fragment_id", f"duplicate id '{fragment_id}'"))
    else:
        ids.add(fragment_id)
    valid_order = isinstance(order, int) and not isinstance(order, bool) and order >= 0
    if valid_order:
        orders.append(order)
    else:
        errors.append(_issue("invalid_fragment_order", f"{path}.order", "order must be a non-negative integer"))
    return valid_order


def _validate_fragment_times(start, fragment_duration, path, errors):
    valid_start = _is_finite_number(start) and start >= 0
    valid_duration = _is_finite_number(fragment_duration) and fragment_duration > 0
    if not valid_start:
        errors.append(_issue("invalid_fragment_start", f"{path}.global_start_seconds", "start must be a finite number greater than or equal to zero"))
    if not valid_duration:
        errors.append(_issue("invalid_fragment_duration", f"{path}.duration_seconds", "duration must be a finite number greater than zero"))
    return valid_start, valid_duration


def _validate_fragment_paths(fragment, path, session_dir, errors, check_files):
    _resolve_source_path(fragment.get("video_path"), session_dir, f"{path}.video_path", errors, check_files)
    if fragment.get("audio_path") is not None:
        _resolve_source_path(fragment["audio_path"], session_dir, f"{path}.audio_path", errors, check_files)


def _validate_fragment(
    fragment: Any,
    path: str,
    ids: set[str],
    orders: list[int],
    normalized: list[tuple[int, float, float, str]],
    errors: list[dict[str, str]],
    session_dir: Path,
    check_files: bool,
) -> None:
    if not isinstance(fragment, dict):
        errors.append(_issue("invalid_fragment", path, "fragment must be an object"))
        return
    _validate_fragment_schema(fragment, path, errors)
    fragment_id, order = fragment.get("fragment_id"), fragment.get("order")
    start, fragment_duration = fragment.get("global_start_seconds"), fragment.get("duration_seconds")
    valid_order = _validate_fragment_identity(fragment_id, order, path, ids, orders, errors)
    valid_start, valid_duration = _validate_fragment_times(start, fragment_duration, path, errors)
    if valid_order and valid_start and valid_duration:
        normalized.append((order, float(start), float(fragment_duration), path))
    _validate_fragment_paths(fragment, path, session_dir, errors, check_files)


def _validate_timeline(normalized, duration, policy, tolerance, errors, warnings):
    if not normalized or not _is_finite_number(duration):
        return
    normalized.sort(key=lambda item: item[0])
    previous_end = None
    for _, start, fragment_duration, path in normalized:
        end = start + fragment_duration
        if end > float(duration) + tolerance:
            errors.append(_issue("fragment_exceeds_session_duration", path, "fragment ends after duration_seconds"))
        if previous_end is None:
            if abs(start) > tolerance:
                errors.append(_issue("timeline_does_not_start_at_zero", path, "first fragment must start at session time zero"))
        else:
            delta = start - previous_end
            if delta < 0:
                errors.append(_issue("fragment_overlap", path, f"fragment overlaps the previous fragment by {-delta:.3f}s"))
            elif delta > 0:
                issue = _issue("timeline_gap", path, f"timeline has a {delta:.3f}s gap before this fragment")
                (errors if policy == "contiguous" and delta > tolerance else warnings).append(issue)
        previous_end = end
    final_end = normalized[-1][1] + normalized[-1][2]
    if abs(float(duration) - final_end) > tolerance:
        errors.append(_issue("session_duration_mismatch", "duration_seconds", "duration must match the final fragment end"))


def validate_session_manifest(
    payload: Any,
    session_dir: Path,
    *,
    check_files: bool = True,
    tolerance_seconds: float = 0.05,
) -> dict[str, Any]:
    """Return a structured report; validation never modifies source files."""
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if not _is_finite_number(tolerance_seconds) or tolerance_seconds < 0:
        return {
            "valid": False,
            "errors": [_issue("invalid_tolerance", "tolerance_seconds", "tolerance must be finite and non-negative")],
            "warnings": [],
        }
    if not isinstance(payload, dict):
        return {
            "valid": False,
            "errors": [_issue("invalid_manifest", "$", "manifest root must be an object")],
            "warnings": [],
        }

    required = {
        "schema_version",
        "session_id",
        "source_version",
        "clock",
        "timeline_policy",
        "duration_seconds",
        "participants",
        "fragments",
    }
    for key in sorted(required - payload.keys()):
        errors.append(_issue("required_field_missing", key, f"required field '{key}' is missing"))
    for key in sorted(payload.keys() - required):
        errors.append(_issue("unknown_field", key, f"field '{key}' is not in manifest schema 1.0"))
    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings}

    if payload["schema_version"] != SCHEMA_VERSION:
        errors.append(_issue("unsupported_schema_version", "schema_version", f"expected {SCHEMA_VERSION}"))
    if not isinstance(payload["session_id"], str) or not payload["session_id"].strip():
        errors.append(_issue("invalid_session_id", "session_id", "session_id must be a non-empty string"))
    if not isinstance(payload["source_version"], str) or not payload["source_version"].strip():
        errors.append(_issue("invalid_source_version", "source_version", "source_version must be a non-empty string"))
    if payload["clock"] != CLOCK:
        errors.append(_issue("unsupported_clock", "clock", f"clock must be '{CLOCK}'"))
    policy = payload["timeline_policy"]
    if not isinstance(policy, str) or policy not in TIMELINE_POLICIES:
        errors.append(_issue("invalid_timeline_policy", "timeline_policy", "expected contiguous or preserve_gaps"))

    duration = payload["duration_seconds"]
    if not _is_finite_number(duration) or duration <= 0:
        errors.append(_issue("invalid_session_duration", "duration_seconds", "duration must be a finite number greater than zero"))

    participants = payload["participants"]
    if not isinstance(participants, list):
        errors.append(_issue("invalid_participants", "participants", "participants must be an array"))
    else:
        participant_ids: set[str] = set()
        for index, participant in enumerate(participants):
            _validate_participant(participant, f"participants[{index}]", participant_ids, errors)

    fragments = payload["fragments"]
    if not isinstance(fragments, list) or not fragments:
        errors.append(_issue("invalid_fragments", "fragments", "fragments must be a non-empty array"))
        fragments = []

    ids: set[str] = set()
    orders: list[int] = []
    normalized: list[tuple[int, float, float, str]] = []
    for index, fragment in enumerate(fragments):
        _validate_fragment(fragment, f"fragments[{index}]", ids, orders, normalized, errors, session_dir, check_files)

    if orders and sorted(orders) != list(range(len(fragments))):
        errors.append(_issue("fragment_order_not_contiguous", "fragments", "order values must be unique and contiguous starting at zero"))
    if len(normalized) == len(fragments):
        _validate_timeline(normalized, duration, policy, tolerance_seconds, errors, warnings)

    return {
        "valid": not errors,
        "session_id": payload.get("session_id"),
        "schema_version": payload.get("schema_version"),
        "fragments_total": len(fragments),
        "duration_seconds": duration if _is_finite_number(duration) else None,
        "errors": errors,
        "warnings": warnings,
    }


def load_and_validate_session_manifest(
    manifest_path: Path,
    *,
    check_files: bool = True,
    tolerance_seconds: float = 0.05,
) -> dict[str, Any]:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "valid": False,
            "errors": [_issue("manifest_read_failed", str(manifest_path), str(error))],
            "warnings": [],
        }
    return validate_session_manifest(
        payload,
        manifest_path.parent,
        check_files=check_files,
        tolerance_seconds=tolerance_seconds,
    )
