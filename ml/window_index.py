"""Build and validate a stable index of synchronized session windows."""

from __future__ import annotations

import bisect
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = "1.0"
SEGMENTS_PATH = Path("processed/segments/segments.json")
AUDIO_FEATURES_PATH = Path("processed/features/audio_features.json")
VISUAL_FEATURES_PATH = Path("processed/features/visual_motion.json")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected_json_object:{path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_timestamp_values(values, name):
    if not isinstance(values, list) or not values:
        raise ValueError(f"invalid_feature_timestamps:{name}")
    result = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"invalid_feature_timestamp:{name}")
        timestamp = float(value)
        if result and timestamp <= result[-1]:
            raise ValueError(f"feature_timestamps_not_strictly_increasing:{name}")
        result.append(timestamp)
    return result


def _validate_feature_series(payload, name, timestamp_count):
    for key, series in payload.items():
        if key == "timestamps" or not isinstance(series, list):
            continue
        if len(series) != timestamp_count:
            raise ValueError(f"feature_array_length_mismatch:{name}:{key}")
        if any(
            isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item)
            for item in series
        ):
            raise ValueError(f"invalid_feature_value:{name}:{key}")


def _timestamps(payload: dict[str, Any], name: str) -> list[float]:
    values = payload.get("timestamps")
    result = _validate_timestamp_values(values, name)
    _validate_feature_series(payload, name, len(result))
    return result


def _feature_range(
    timestamps: list[float], start: float, end: float, path: str
) -> dict[str, Any]:
    first = bisect.bisect_left(timestamps, start)
    stop = bisect.bisect_left(timestamps, end)
    if first == stop:
        raise ValueError(f"no_feature_samples_in_window:{path}:{start:g}-{end:g}")
    return {
        "path": path,
        "start_index": first,
        "end_index_exclusive": stop,
        "sample_count": stop - first,
        "first_timestamp_seconds": timestamps[first],
        "last_timestamp_seconds": timestamps[stop - 1],
    }


def _safe_segment_path(session_dir: Path, relative: Any, field: str) -> str:
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"invalid_segment_reference:{field}")
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise ValueError(f"unsafe_segment_reference:{field}")
    full_path = session_dir / "processed" / "segments" / Path(*path.parts)
    root = (session_dir / "processed" / "segments").resolve()
    try:
        full_path.resolve().relative_to(root)
    except ValueError:
        raise ValueError(f"unsafe_segment_reference:{field}") from None
    if not full_path.is_file():
        raise ValueError(f"missing_segment_file:{field}")
    return full_path.relative_to(session_dir).as_posix()


def _validate_segment_entry(segment, index, previous_end, window_seconds, drift_tolerance):
    if not isinstance(segment, dict):
        raise ValueError(f"invalid_segment:{index}")
    start, end, duration = (segment.get(key) for key in ("start_seconds", "end_seconds", "duration_seconds"))
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in (start, end, duration)):
        raise ValueError(f"invalid_segment_time:{index}")
    start, end, duration = float(start), float(end), float(duration)
    if abs(start - previous_end) > 1e-6 or abs(end - start - duration) > 1e-6:
        raise ValueError(f"segment_timeline_gap_or_duration_mismatch:{index}")
    if abs(start - index * window_seconds) > 1e-6 or segment.get("index") != index:
        raise ValueError(f"segment_index_or_grid_invalid:{index}")
    sync_drift = segment.get("sync_drift_seconds")
    if isinstance(sync_drift, bool) or not isinstance(sync_drift, (int, float)) or not math.isfinite(sync_drift) or sync_drift > drift_tolerance:
        raise ValueError(f"segment_sync_drift_invalid:{index}")
    return start, end, duration, float(sync_drift)


def _window_from_segment(session_dir, segment, index, session_id, start, end, duration, sync_drift, window_seconds, audio_timestamps, visual_timestamps):
    video_ref = _safe_segment_path(session_dir, segment.get("video"), f"{index}:video")
    audio_ref = _safe_segment_path(session_dir, segment.get("audio"), f"{index}:audio")
    if duration < window_seconds - 1e-6:
        return None, {
            "segment_index": index, "start_seconds": start, "end_seconds": end,
            "duration_seconds": duration, "reason": "partial_window_shorter_than_configured_window",
            "video_path": video_ref, "audio_path": audio_ref,
        }
    if abs(duration - window_seconds) > 1e-6:
        raise ValueError(f"segment_longer_than_configured_window:{index}")
    return {
        "window_id": f"{session_id}_W{index:04d}", "index": index, "session_id": session_id,
        "start_seconds": start, "end_seconds": end, "duration_seconds": duration,
        "segment": {"index": index, "video_path": video_ref, "audio_path": audio_ref, "sync_drift_seconds": sync_drift},
        "feature_samples": {
            "audio": _feature_range(audio_timestamps, start, end, AUDIO_FEATURES_PATH.as_posix()),
            "visual": _feature_range(visual_timestamps, start, end, VISUAL_FEATURES_PATH.as_posix()),
        },
    }, None


def build_window_index(session_dir: Path) -> dict[str, Any]:
    """Build a window index; retain only full windows and report partial tails."""
    segments_payload = _read_json(session_dir / SEGMENTS_PATH)
    audio_payload = _read_json(session_dir / AUDIO_FEATURES_PATH)
    visual_payload = _read_json(session_dir / VISUAL_FEATURES_PATH)
    session_id = segments_payload.get("session_id")
    window_seconds = segments_payload.get("window_seconds")
    segments = segments_payload.get("segments")
    if not isinstance(session_id, str) or not session_id or session_id != session_dir.name:
        raise ValueError("segments_session_id_mismatch")
    if (
        isinstance(window_seconds, bool)
        or not isinstance(window_seconds, (int, float))
        or not math.isfinite(window_seconds)
        or window_seconds <= 0
    ):
        raise ValueError("invalid_segment_window_seconds")
    if not isinstance(segments, list) or not segments:
        raise ValueError("segments_missing_or_empty")

    audio_timestamps = _timestamps(audio_payload, "audio")
    visual_timestamps = _timestamps(visual_payload, "visual")
    windows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    previous_end = 0.0

    drift_tolerance = float(segments_payload.get("drift_tolerance_seconds", 0.15))
    for index, segment in enumerate(segments):
        start, end, duration, sync_drift = _validate_segment_entry(
            segment, index, previous_end, float(window_seconds), drift_tolerance
        )
        previous_end = end
        window, partial = _window_from_segment(
            session_dir, segment, index, session_id, start, end, duration, sync_drift,
            float(window_seconds), audio_timestamps, visual_timestamps,
        )
        if window is not None:
            windows.append(window)
        else:
            excluded.append(partial)

    source_paths = (SEGMENTS_PATH, AUDIO_FEATURES_PATH, VISUAL_FEATURES_PATH)
    duration = float(segments_payload.get("effective_duration_seconds", previous_end))
    complete_duration = len(windows) * float(window_seconds)
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "clock": segments_payload.get("clock"),
        "window_seconds": float(window_seconds),
        "window_policy": "include_full_windows_only; exclude_partial_tail",
        "duration_seconds": duration,
        "complete_windows": len(windows),
        "complete_coverage_seconds": complete_duration,
        "excluded_partial_duration_seconds": round(max(0.0, duration - complete_duration), 6),
        "source_artifacts": {
            path.as_posix(): {"sha256": _sha256(session_dir / path)}
            for path in source_paths
        },
        "windows": windows,
        "excluded_segments": excluded,
        "training_authorized": False,
        "notice": "Window index only; this does not authorize training or validate labels.",
    }


def _validate_segment_references(session_dir, segment, index):
    issues = []
    for field in ("video_path", "audio_path"):
        value = segment.get(field)
        if not isinstance(value, str):
            issues.append(f"segment_reference_missing:{index}:{field}")
            continue
        try:
            path = PurePosixPath(value)
            resolved = (session_dir / Path(*path.parts)).resolve()
            resolved.relative_to(session_dir.resolve())
            if not resolved.is_file():
                issues.append(f"segment_file_missing:{index}:{field}")
        except (ValueError, OSError):
            issues.append(f"unsafe_segment_reference:{index}:{field}")
    return issues


def _validate_feature_range(session_dir, sample_range, modality, index, start, end):
    if not isinstance(sample_range, dict):
        return [f"feature_range_missing:{index}:{modality}"]
    path = sample_range.get("path")
    start_index, end_index = sample_range.get("start_index"), sample_range.get("end_index_exclusive")
    if not isinstance(path, str) or not isinstance(start_index, int) or not isinstance(end_index, int) or start_index < 0 or end_index <= start_index or sample_range.get("sample_count") != end_index - start_index:
        return [f"feature_range_invalid:{index}:{modality}"]
    try:
        feature_path = session_dir / path
        feature_path.resolve().relative_to(session_dir.resolve())
        timestamps = _timestamps(_read_json(feature_path), modality)
        if end_index > len(timestamps):
            return [f"feature_range_out_of_bounds:{index}:{modality}"]
        if not (float(start) <= timestamps[start_index] < float(end) and float(start) <= timestamps[end_index - 1] < float(end)):
            return [f"feature_timestamp_outside_window:{index}:{modality}"]
    except (OSError, ValueError):
        return [f"feature_source_invalid:{index}:{modality}"]
    return []


def _validate_window_entry(session_dir, window, index, session_id, expected_start, window_seconds):
    issues = []
    if not isinstance(window, dict):
        return [f"invalid_window:{index}"], expected_start + window_seconds
    start, end = window.get("start_seconds"), window.get("end_seconds")
    if window.get("window_id") != f"{session_id}_W{index:04d}":
        issues.append(f"unstable_window_id:{index}")
    if window.get("index") != index:
        issues.append(f"window_index_not_contiguous:{index}")
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or abs(float(start) - expected_start) > 1e-6 or abs(float(end) - float(start) - float(window_seconds)) > 1e-6:
        issues.append(f"window_timeline_invalid:{index}")
    segment, features = window.get("segment"), window.get("feature_samples")
    if not isinstance(segment, dict) or not isinstance(features, dict):
        return issues + [f"window_references_missing:{index}"], expected_start + float(window_seconds)
    issues.extend(_validate_segment_references(session_dir, segment, index))
    for modality in ("audio", "visual"):
        issues.extend(_validate_feature_range(session_dir, features.get(modality), modality, index, start, end))
    return issues, expected_start + float(window_seconds)


def _validate_source_artifacts(session_dir, source_artifacts):
    if not isinstance(source_artifacts, dict):
        return ["source_artifacts_missing"]
    issues = []
    for relative_path, record in source_artifacts.items():
        if not isinstance(record, dict) or not isinstance(record.get("sha256"), str):
            issues.append(f"source_hash_missing:{relative_path}")
            continue
        relative = PurePosixPath(relative_path)
        if relative.is_absolute() or ".." in relative.parts or "\\" in relative_path:
            issues.append(f"unsafe_source_path:{relative_path}")
            continue
        path = session_dir / Path(*relative.parts)
        if not path.is_file() or _sha256(path) != record["sha256"]:
            issues.append(f"source_hash_mismatch:{relative_path}")
    return issues


def validate_window_index(index: dict[str, Any], session_dir: Path) -> list[str]:
    """Validate window IDs, timeline, file references, feature ranges, and hashes."""
    issues: list[str] = []
    session_id = index.get("session_id")
    if index.get("schema_version") != SCHEMA_VERSION:
        issues.append("unsupported_schema_version")
    if session_id != session_dir.name:
        issues.append("session_id_mismatch")
    window_seconds = index.get("window_seconds")
    windows = index.get("windows")
    if not isinstance(windows, list) or not windows:
        issues.append("windows_missing_or_empty")
        return issues
    if (
        isinstance(window_seconds, bool)
        or not isinstance(window_seconds, (int, float))
        or not math.isfinite(window_seconds)
        or window_seconds <= 0
    ):
        issues.append("invalid_window_seconds")
        return issues

    expected_start = 0.0
    for expected_index, window in enumerate(windows):
        entry_issues, expected_start = _validate_window_entry(
            session_dir, window, expected_index, session_id, expected_start, window_seconds
        )
        issues.extend(entry_issues)

    issues.extend(_validate_source_artifacts(session_dir, index.get("source_artifacts")))
    return issues
