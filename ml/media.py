"""Reuse the dataset's FFmpeg extraction stages and build synchronized clips."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from session_manifest import load_and_validate_session_manifest
from infraestructura.medios import AdaptadorFFmpeg


_ffmpeg = AdaptadorFFmpeg()


def run_command(command: list[str]) -> str:
    return _ffmpeg.ejecutar(command)


def run_existing_extraction(
    session_id: str, project_root: Path, overwrite: bool = False
) -> dict[str, str]:
    """Run existing normalization/features scripts only when outputs are absent."""
    session_dir = project_root / "dataset" / "dataset" / "sessions" / session_id
    metadata_path = session_dir / "metadata" / "session.json"
    manifest_path = session_dir / "session_manifest.json"
    manifest_mode = manifest_path.is_file()
    if not metadata_path.is_file():
        raise FileNotFoundError(f"missing session metadata: {metadata_path}")
    json.loads(metadata_path.read_text(encoding="utf-8"))
    video = session_dir / "processed" / "video" / f"{session_id}_1280x720_10fps.mp4"
    audio = session_dir / "processed" / "audio" / f"{session_id}_16khz_mono.wav"
    frames_dir = session_dir / "processed" / "frames"
    features_dir = session_dir / "processed" / "features"
    audio_features = features_dir / "audio_features.json"
    visual_features = features_dir / "visual_motion.json"

    scripts_dir = project_root / "dataset" / "scripts"

    stages, manifest_regenerated = _run_extraction_stages(
        session_id, project_root, session_dir, manifest_path, manifest_mode,
        video, audio, frames_dir, audio_features, visual_features, scripts_dir, overwrite,
    )

    required = (video, audio, audio_features, visual_features)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("extraction did not produce required outputs: " + ", ".join(missing))
    return stages


def _run_extraction_stages(session_id, project_root, session_dir, manifest_path, manifest_mode, video, audio, frames_dir, audio_features, visual_features, scripts_dir, overwrite):
    invoke = lambda script, force=False: _invoke_extraction(
        script, session_id, project_root, scripts_dir, overwrite or force
    )
    stages, regenerated = _normalize_extraction(
        session_id, session_dir, manifest_path, manifest_mode,
        video, audio, overwrite, invoke,
    )
    frames_exist = frames_dir.is_dir() and any(frames_dir.glob(f"{session_id}_*.jpg"))
    if overwrite or regenerated or not frames_exist:
        invoke("extraer_frames.py", force_overwrite=regenerated)
        stages["extract_frames"] = "executed"
    else:
        stages["extract_frames"] = "reused"
    if overwrite or regenerated or not audio_features.is_file() or not visual_features.is_file():
        invoke("extraer_features.py", force_overwrite=regenerated)
        stages["extract_features"] = "executed"
    else:
        stages["extract_features"] = "reused"
    return stages, regenerated


def _invoke_extraction(script_name, session_id, project_root, scripts_dir, overwrite):
    command = [sys.executable, str(scripts_dir / script_name), session_id, "--raiz", str(project_root / "dataset")]
    if overwrite:
        command.append("--sobrescribir")
    subprocess.run(command, check=True)


def _normalize_extraction(session_id, session_dir, manifest_path, manifest_mode, video, audio, overwrite, invoke):
    if manifest_mode:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if payload.get("session_id") != session_id:
            raise ValueError(f"manifest session_id {payload.get('session_id')} does not match {session_id}")
        result = normalize_manifest_fragments(session_dir, manifest_path, overwrite=overwrite)
        return {"normalize_audio_video": result["status"]}, result["status"] == "executed"
    if overwrite or not video.is_file() or not audio.is_file():
        invoke("procesar_sesion.py")
        return {"normalize_audio_video": "executed"}, False
    return {"normalize_audio_video": "reused"}, False


def _create_gap_parts(staging, index, gap):
    gap_video = staging / f"part-{index:06d}-gap.mp4"
    gap_audio = staging / f"part-{index:06d}-gap.wav"
    run_command([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
        "-i", "color=c=black:s=1280x720:r=10", "-t", f"{gap:.9f}", "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        str(gap_video),
    ])
    run_command([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
        "-i", "anullsrc=channel_layout=mono:sample_rate=16000", "-t", f"{gap:.9f}",
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(gap_audio),
    ])
    return gap_video, gap_audio


def _create_video_part(staging, index, source_video, duration):
    output = staging / f"part-{index:06d}-video.mp4"
    run_command([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source_video),
        "-t", f"{duration:.9f}", "-vf",
        "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=10,setpts=PTS-STARTPTS",
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        str(output),
    ])
    return output


def _create_audio_part(staging, index, source_video, source_audio, duration, has_audio, tolerance):
    output = staging / f"part-{index:06d}-audio.wav"
    if has_audio:
        if probe_stream_duration(source_audio, "a:0") + tolerance < duration:
            raise ValueError(f"audio source is shorter than manifest fragment for {source_audio}")
        command = [
            "-i", str(source_audio), "-t", f"{duration:.9f}", "-vn",
            "-af", "asetpts=PTS-STARTPTS,aresample=16000",
        ]
    else:
        command = [
            "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=16000",
            "-t", f"{duration:.9f}",
        ]
    run_command([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *command,
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output),
    ])
    return output


def _process_manifest_fragment(staging, manifest_path, fragment, index, previous_end, policy, tolerance):
    start = float(fragment["global_start_seconds"])
    duration = float(fragment["duration_seconds"])
    gap = start - previous_end
    if gap < 0:
        raise ValueError(f"fragment {fragment['fragment_id']} overlaps its predecessor; overlapping media cannot be concatenated without losing timeline data")
    video_parts, audio_parts = [], []
    if gap > 0:
        if policy != "preserve_gaps" and gap > tolerance:
            raise ValueError("manifest has a timeline gap but policy is contiguous")
        gap_video, gap_audio = _create_gap_parts(staging, index, gap)
        video_parts.append(gap_video)
        audio_parts.append(gap_audio)
    source_video = manifest_path.parent / fragment["video_path"]
    if probe_stream_duration(source_video, "v:0") + tolerance < duration:
        raise ValueError(f"video source is shorter than manifest fragment {fragment['fragment_id']}")
    video_parts.append(_create_video_part(staging, index, source_video, duration))
    source_audio = manifest_path.parent / fragment["audio_path"] if fragment.get("audio_path") else source_video
    has_audio = bool(fragment.get("audio_path")) or _has_audio_stream(source_video)
    audio_parts.append(_create_audio_part(staging, index, source_video, source_audio, duration, has_audio, tolerance))
    return video_parts, audio_parts, start + duration


def _manifest_context(session_dir, manifest_path, payload):
    session_id = payload["session_id"]
    if session_dir.name != session_id:
        raise ValueError(f"manifest session_id {session_id} does not match session directory {session_dir.name}")
    sources = sorted({
        manifest_path.parent / path
        for fragment in payload["fragments"]
        for path in (fragment["video_path"], fragment.get("audio_path"))
        if path
    })
    source_hashes = {str(path.relative_to(manifest_path.parent)): _sha256_file(path) for path in sources}
    processed = session_dir / "processed"
    video_dir, audio_dir = processed / "video", processed / "audio"
    video_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    return (
        processed, video_dir / f"{session_id}_1280x720_10fps.mp4",
        audio_dir / f"{session_id}_16khz_mono.wav",
        processed / "manifest_processing.json", source_hashes,
        hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )


def _reuse_normalized_outputs(video_output, audio_output, provenance_path, manifest_digest, source_hashes, overwrite):
    if not (video_output.is_file() or audio_output.is_file()) or overwrite:
        return None
    if provenance_path.is_file():
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        if (
            provenance.get("manifest_sha256") == manifest_digest
            and provenance.get("source_sha256") == source_hashes
            and video_output.is_file() and audio_output.is_file()
        ):
            return {"status": "reused", **provenance}
    raise FileExistsError("normalized outputs already exist or belong to another manifest; pass overwrite=True to regenerate")


def _concat_manifest_parts(staging, video_parts, audio_parts):
    video_list, audio_list = staging / "video.txt", staging / "audio.txt"
    _concat_file_list(video_parts, video_list)
    _concat_file_list(audio_parts, audio_list)
    staged_video, staged_audio = staging / "normalized.mp4", staging / "normalized.wav"
    run_command([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
        "-i", str(video_list), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", str(staged_video),
    ])
    run_command([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
        "-i", str(audio_list), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(staged_audio),
    ])
    return staged_video, staged_audio


def _write_manifest_provenance(staging, provenance_path, provenance):
    temporary = staging / "manifest_processing.json"
    temporary.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, provenance_path)


def probe_duration(path: Path) -> float:
    value = run_command([
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ])
    duration = float(value)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"invalid media duration for {path}")
    return duration


def _fallback_stream_duration(path, stream_selector):
    try:
        details = json.loads(run_command([
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration:stream=codec_type", "-of", "json", str(path),
        ]))
        streams = details.get("streams", [])
        duration = float(details["format"]["duration"])
        if len(streams) != 1:
            raise ValueError("container has multiple streams")
        return duration
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"could not read {stream_selector} duration for {path}") from error


def probe_stream_duration(path: Path, stream_selector: str) -> float:
    """Read a specific stream duration, not the container's longest-stream duration."""
    value = run_command([
        "ffprobe", "-v", "error", "-select_streams", stream_selector,
        "-show_entries", "stream=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    try:
        duration = float(value.splitlines()[0])
    except (IndexError, ValueError):
        # Some containers (notably Matroska) omit per-stream duration. A
        # container duration is safe only when there is exactly one stream;
        # otherwise it could mask audio/video drift by reporting the longest.
        duration = _fallback_stream_duration(path, stream_selector)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"invalid {stream_selector} duration for {path}")
    return duration


def _has_audio_stream(path: Path) -> bool:
    output = run_command([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path),
    ])
    return bool(output)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as media_file:
        for block in iter(lambda: media_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _concat_file_list(paths: list[Path], output_path: Path) -> None:
    lines = []
    for path in paths:
        # Staging uses generated filenames, but quote defensively for FFmpeg's
        # concat-demuxer syntax.
        escaped = str(path).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def normalize_manifest_fragments(
    session_dir: Path,
    manifest_path: Path | None = None,
    *,
    overwrite: bool = False,
    tolerance_seconds: float = 0.15,
) -> dict[str, Any]:
    """Normalize and concatenate manifest fragments without changing raw inputs."""
    manifest_path = manifest_path or session_dir / "session_manifest.json"
    report = load_and_validate_session_manifest(
        manifest_path,
        check_files=True,
        tolerance_seconds=tolerance_seconds,
    )
    if not report["valid"]:
        codes = ", ".join(issue["code"] for issue in report["errors"])
        raise ValueError(f"session manifest is invalid: {codes}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    session_id = payload["session_id"]
    processed, video_output, audio_output, provenance_path, source_hashes, manifest_digest = _manifest_context(
        session_dir, manifest_path, payload
    )
    reused = _reuse_normalized_outputs(
        video_output, audio_output, provenance_path, manifest_digest, source_hashes, overwrite
    )
    if reused is not None:
        return reused

    staging = Path(tempfile.mkdtemp(prefix=".manifest-media-", dir=processed))
    video_parts: list[Path] = []
    audio_parts: list[Path] = []
    previous_end = 0.0
    try:
        for index, fragment in enumerate(payload["fragments"]):
            fragment_video, fragment_audio, previous_end = _process_manifest_fragment(
                staging, manifest_path, fragment, index, previous_end,
                payload["timeline_policy"], tolerance_seconds,
            )
            video_parts.extend(fragment_video)
            audio_parts.extend(fragment_audio)

        staged_video, staged_audio = _concat_manifest_parts(staging, video_parts, audio_parts)
        video_duration = probe_stream_duration(staged_video, "v:0")
        audio_duration = probe_stream_duration(staged_audio, "a:0")
        expected_duration = float(payload["duration_seconds"])
        if abs(video_duration - expected_duration) > tolerance_seconds:
            raise ValueError(
                f"normalized video duration {video_duration:.3f}s differs from "
                f"manifest duration {expected_duration:.3f}s"
            )
        if abs(audio_duration - expected_duration) > tolerance_seconds:
            raise ValueError(
                f"normalized audio duration {audio_duration:.3f}s differs from "
                f"manifest duration {expected_duration:.3f}s"
            )

        os.replace(staged_video, video_output)
        os.replace(staged_audio, audio_output)
        provenance = {
            "schema_version": "1.0",
            "session_id": session_id,
            "manifest_sha256": manifest_digest,
            "source_sha256": source_hashes,
            "source_version": payload["source_version"],
            "fragments_total": len(payload["fragments"]),
            "duration_seconds": expected_duration,
            "video_duration_seconds": round(video_duration, 6),
            "audio_duration_seconds": round(audio_duration, 6),
            "timeline_policy": payload["timeline_policy"],
        }
        _write_manifest_provenance(staging, provenance_path, provenance)
        return {"status": "executed", **provenance}
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _reuse_segments(output_root, manifest_path, window_seconds, drift_tolerance_seconds, max_tail_trim_seconds):
    if not manifest_path.is_file():
        return None
    existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    matches = (
        existing.get("window_seconds") == window_seconds
        and existing.get("drift_tolerance_seconds") == drift_tolerance_seconds
        and existing.get("max_tail_trim_seconds") == max_tail_trim_seconds
    )
    files_exist = all(
        (output_root / segment["video"]).is_file() and (output_root / segment["audio"]).is_file()
        for segment in existing.get("segments", [])
    )
    return existing if matches and files_exist else None


def _segment_window(staging, video, audio, index, start, duration, drift_tolerance_seconds):
    window_dir = staging / f"window_{index:06d}"
    window_dir.mkdir()
    video_out, audio_out = window_dir / "video.mp4", window_dir / "audio.wav"
    common = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    run_command([
        *common, "-ss", f"{start:.6f}", "-i", str(video), "-t", f"{duration:.6f}",
        "-map", "0:v:0", "-an", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "23", "-pix_fmt", "yuv420p", str(video_out),
    ])
    run_command([
        *common, "-ss", f"{start:.6f}", "-i", str(audio), "-t", f"{duration:.6f}",
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio_out),
    ])
    video_duration = probe_stream_duration(video_out, "v:0")
    audio_duration = probe_stream_duration(audio_out, "a:0")
    drift = abs(video_duration - audio_duration)
    if drift > drift_tolerance_seconds:
        raise ValueError(f"window drift {drift:.3f}s exceeds {drift_tolerance_seconds:.3f}s")
    return {
        "index": index, "start_seconds": round(start, 6),
        "end_seconds": round(start + duration, 6), "duration_seconds": round(duration, 6),
        "video": f"window_{index:06d}/video.mp4", "audio": f"window_{index:06d}/audio.wav",
        "video_duration_seconds": round(video_duration, 6),
        "audio_duration_seconds": round(audio_duration, 6), "sync_drift_seconds": round(drift, 6),
    }, drift


def _segment_manifest(session_id, window_seconds, common_duration, video_duration, audio_duration, source_drift, trimmed_stream, max_tail_trim_seconds, drift_tolerance_seconds, records, max_segment_drift):
    return {
        "schema_version": "1.0", "session_id": session_id,
        "clock": "seconds from the start of the normalized session",
        "window_seconds": window_seconds, "effective_duration_seconds": round(common_duration, 6),
        "source_durations_seconds": {"video": round(video_duration, 6), "audio": round(audio_duration, 6)},
        "source_drift_seconds": round(source_drift, 6), "trimmed_stream": trimmed_stream,
        "tail_trim_seconds": round(source_drift, 6),
        "tail_trim_policy": "trim_longer_stream_to_shorter",
        "max_tail_trim_seconds": max_tail_trim_seconds,
        "max_segment_drift_seconds": round(max_segment_drift, 6),
        "drift_tolerance_seconds": drift_tolerance_seconds, "segments": records,
    }


def _segment_source_info(video, audio, max_tail_trim_seconds):
    video_duration = probe_stream_duration(video, "v:0")
    audio_duration = probe_stream_duration(audio, "a:0")
    source_drift = abs(video_duration - audio_duration)
    if source_drift > max_tail_trim_seconds:
        raise ValueError(f"source streams differ by {source_drift:.3f}s (maximum tail trim {max_tail_trim_seconds:.3f}s)")
    trimmed_stream = "audio" if audio_duration > video_duration else "video" if video_duration > audio_duration else None
    return video_duration, audio_duration, source_drift, trimmed_stream, min(video_duration, audio_duration)


def _write_segment_manifest(staging, output_root, manifest):
    (staging / "segments.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if output_root.exists():
        shutil.rmtree(output_root)
    staging.replace(output_root)


def _build_segments(staging, video, audio, window_seconds, common_duration, drift_tolerance_seconds):
    records, max_segment_drift = [], 0.0
    for index in range(math.ceil(common_duration / window_seconds)):
        start = index * window_seconds
        duration = min(window_seconds, common_duration - start)
        record, drift = _segment_window(
            staging, video, audio, index, start, duration, drift_tolerance_seconds,
        )
        records.append(record)
        max_segment_drift = max(max_segment_drift, drift)
    return records, max_segment_drift


def segment_and_synchronize(
    session_dir: Path,
    session_id: str,
    window_seconds: float = 5.0,
    drift_tolerance_seconds: float = 0.15,
    max_tail_trim_seconds: float = 0.20,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Cut synchronized streams, trimming only a bounded trailing duration."""
    if any(not math.isfinite(value) for value in (window_seconds, drift_tolerance_seconds, max_tail_trim_seconds)) or window_seconds <= 0 or drift_tolerance_seconds <= 0 or max_tail_trim_seconds < 0:
        raise ValueError("window/drift tolerance must be positive and tail trim non-negative")
    video = session_dir / "processed" / "video" / f"{session_id}_1280x720_10fps.mp4"
    audio = session_dir / "processed" / "audio" / f"{session_id}_16khz_mono.wav"
    if not video.is_file() or not audio.is_file():
        raise FileNotFoundError("normalized video and audio are required before segmentation")

    output_root = session_dir / "processed" / "segments"
    manifest_path = output_root / "segments.json"
    if output_root.exists() and not overwrite:
        existing = _reuse_segments(
            output_root, manifest_path, window_seconds,
            drift_tolerance_seconds, max_tail_trim_seconds,
        )
        if existing is not None:
            return existing
        raise FileExistsError(f"segments exist at {output_root}; pass overwrite=True to regenerate")

    video_duration, audio_duration, source_drift, trimmed_stream, common_duration = _segment_source_info(
        video, audio, max_tail_trim_seconds
    )

    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".segments-", dir=output_root.parent))
    try:
        records, max_segment_drift = _build_segments(
            staging, video, audio, window_seconds, common_duration, drift_tolerance_seconds
        )
        manifest = _segment_manifest(
            session_id, window_seconds, common_duration, video_duration, audio_duration,
            source_drift, trimmed_stream, max_tail_trim_seconds, drift_tolerance_seconds,
            records, max_segment_drift,
        )
        _write_segment_manifest(staging, output_root, manifest)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def synchronize_pose_with_segments(
    segment_manifest: dict[str, Any],
    pose_payload: dict[str, Any] | None,
    pose_features_path: str | None,
    *,
    acoustic_payload: dict[str, Any] | None = None,
    acoustic_features_path: str | None = None,
    vocalization_payload: dict[str, Any] | None = None,
    vocalization_features_path: str | None = None,
    movement_payload: dict[str, Any] | None = None,
    movement_features_path: str | None = None,
) -> dict[str, Any]:
    """Join timestamped derived modalities to audio/video windows on session time."""
    pose_frames = pose_payload.get("frames", []) if pose_payload else []
    acoustic_windows = acoustic_payload.get("windows", []) if acoustic_payload else []
    vocalization_candidates = (
        vocalization_payload.get("candidates", []) if vocalization_payload else []
    )
    movement_windows = movement_payload.get("windows", []) if movement_payload else []
    synchronized_segments = []
    for segment in segment_manifest.get("segments", []):
        start = float(segment["start_seconds"])
        end = float(segment["end_seconds"])
        pose_indices = [
            index
            for index, frame in enumerate(pose_frames)
            if start <= float(frame["timestamp_seconds"]) < end
        ]
        acoustic_indices = [
            index
            for index, window in enumerate(acoustic_windows)
            if start <= float(window["timestamp_seconds"]) < end
        ]
        vocalization_indices = [
            index
            for index, candidate in enumerate(vocalization_candidates)
            if float(candidate["start_seconds"]) < end
            and float(candidate["end_seconds"]) > start
        ]
        expected_window_id = f"{segment_manifest['session_id']}_W{int(segment['index']):04d}"
        movement_indices = [
            index
            for index, window in enumerate(movement_windows)
            if window.get("window_id") == expected_window_id
        ]
        if len(movement_indices) > 1:
            raise ValueError(f"duplicate_movement_window:{expected_window_id}")
        synchronized_segments.append({
            **segment,
            "pose_features_path": pose_features_path if pose_payload else None,
            "pose_frame_indices": pose_indices,
            "acoustic_features_path": acoustic_features_path if acoustic_payload else None,
            "acoustic_window_indices": acoustic_indices,
            "vocalization_features_path": (
                vocalization_features_path if vocalization_payload else None
            ),
            "vocalization_candidate_indices": vocalization_indices,
            "movement_features_path": movement_features_path if movement_payload else None,
            "movement_window_index": movement_indices[0] if movement_indices else None,
        })
    return {
        "schema_version": "1.0",
        "session_id": segment_manifest["session_id"],
        "clock": segment_manifest["clock"],
        "window_seconds": segment_manifest["window_seconds"],
        "source_drift_seconds": segment_manifest["source_drift_seconds"],
        "trimmed_stream": segment_manifest.get("trimmed_stream"),
        "tail_trim_seconds": segment_manifest.get("tail_trim_seconds", 0.0),
        "max_segment_drift_seconds": segment_manifest["max_segment_drift_seconds"],
        "pose_sampling_fps": pose_payload.get("sampling_fps") if pose_payload else None,
        "pose_features_path": pose_features_path if pose_payload else None,
        "acoustic_features_path": acoustic_features_path if acoustic_payload else None,
        "vocalization_features_path": (
            vocalization_features_path if vocalization_payload else None
        ),
        "movement_features_path": movement_features_path if movement_payload else None,
        "segments": synchronized_segments,
    }
