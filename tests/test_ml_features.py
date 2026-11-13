import json
import sys
import tempfile
from types import SimpleNamespace
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import numpy as np
import soundfile as sf


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

from demuca_estimates import build_demuca_estimates, write_demuca_estimates
import media
import media_pipeline as media_pipeline_module
from audio_features import extract_audio_modalities
from create_window_index import write_window_index
from media import synchronize_pose_with_segments
from media_pipeline import _PipelineSummaryContext, _build_pipeline_summary, persist_or_reuse_audio_artifact
from movement_interaction import build_movement_interaction_features
from pipeline_graph import write_pipeline_graph
import pose as pose_module
from pose import frame_timestamp_seconds, load_pose_landmarks
from tracking import flatten_metrics
from session_manifest import validate_session_manifest
from validate_multimodal_artifacts import validate_multimodal_artifacts
from window_index import build_window_index, validate_window_index


class MlFeatureTests(TestCase):
    def test_movement_features_track_pose_and_proximity(self):
        landmarks = [{"x": 0.1, "y": 0.2, "visibility": 0.9}]
        first = {"timestamp_seconds": 0.0, "poses": [{"landmarks": landmarks}]}
        second = {"timestamp_seconds": 0.1, "poses": [{"landmarks": [{"x": 0.2, "y": 0.2, "visibility": 0.9}]}]}
        result = build_movement_interaction_features(
            {"session_id": "S1", "sampling_fps": 10, "frames": [first, second]},
            {"session_id": "S1", "window_seconds": 1, "windows": [{"window_id": "S1_W0000", "start_seconds": 0, "end_seconds": 1}]},
        )
        self.assertEqual(result["frames_processed"], 2)
        self.assertEqual(result["windows"][0]["pose_count_max"], 1)
        self.assertGreater(result["frames"][1]["anonymous_joint_centroid_motion_per_second"], 0)

    def test_movement_features_reject_invalid_payloads(self):
        with self.assertRaisesRegex(ValueError, "pose_window_session_mismatch"):
            build_movement_interaction_features(
                {"session_id": "S1", "frames": []}, {"session_id": "S2", "windows": [{}]}
            )
        with self.assertRaisesRegex(ValueError, "invalid_pose_feature_threshold"):
            build_movement_interaction_features(
                {"session_id": "S1", "frames": []},
                {"session_id": "S1", "windows": [{}]},
                visibility_threshold=2,
            )

    def test_demuca_estimates_bound_confidence_and_write_reuses_output(self):
        payload = {
            "session_id": "S1",
            "evaluations": [{
                "patient_id": "P1", "scale": "scale", "review_status": "draft",
                "responses": [{
                    "subscale": "movement", "category": "body", "score": 2,
                    "max_score": 5, "evidence": [{"modality": "audio", "start_seconds": 0, "end_seconds": 1}],
                }],
            }],
        }
        result = build_demuca_estimates(
            payload, session_id="S1", duration_seconds=2,
            available_modalities={"audio"}, source_sha256="a" * 64,
        )
        self.assertEqual(result["confidence_cap_percent"], 49.0)
        self.assertFalse(result["training_authorized"])
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "S1"
            source = session / "annotations" / "demuca"
            source.mkdir(parents=True)
            (session / "metadata").mkdir()
            (source / "evaluations.json").write_text(json.dumps(payload))
            (session / "metadata" / "session.json").write_text(json.dumps({"technical": {"duration_seconds": 2}}))
            output = session / "processed" / "features" / "demuca_estimates.json"
            written = write_demuca_estimates(session, output)
            self.assertEqual(written["session_id"], "S1")
            self.assertEqual(write_demuca_estimates(session, output), written)

    def test_session_manifest_accepts_valid_payload_and_reports_invalid_timeline(self):
        payload = {
            "schema_version": "1.0", "session_id": "S1", "source_version": "v1",
            "clock": "session_elapsed_seconds", "timeline_policy": "contiguous",
            "duration_seconds": 1, "participants": [{"id": "P1", "role": "PATIENT"}],
            "fragments": [{"fragment_id": "F1", "order": 0, "global_start_seconds": 0,
                           "duration_seconds": 1, "video_path": "raw/video.mp4"}],
        }
        valid = validate_session_manifest(payload, Path("/tmp/S1"), check_files=False)
        self.assertTrue(valid["valid"])
        payload["fragments"][0]["global_start_seconds"] = 2
        invalid = validate_session_manifest(payload, Path("/tmp/S1"), check_files=False)
        self.assertFalse(invalid["valid"])
        self.assertTrue(any(issue["code"] == "timeline_does_not_start_at_zero" for issue in invalid["errors"]))

    def test_window_index_builds_full_windows_and_validates_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "S1"
            segments = session / "processed" / "segments"
            features = session / "processed" / "features"
            segments.mkdir(parents=True)
            features.mkdir(parents=True)
            (segments / "video.mp4").write_bytes(b"video")
            (segments / "audio.wav").write_bytes(b"audio")
            (segments / "segments.json").write_text(json.dumps({
                "session_id": "S1", "clock": "seconds", "window_seconds": 1,
                "effective_duration_seconds": 1,
                "segments": [{"index": 0, "start_seconds": 0, "end_seconds": 1,
                              "duration_seconds": 1, "video": "video.mp4", "audio": "audio.wav",
                              "sync_drift_seconds": 0}],
            }))
            for name, values in (("audio_features.json", {"timestamps": [0.2, 0.8], "rms": [1, 2]}),
                                 ("visual_motion.json", {"timestamps": [0.3, 0.7], "motion": [1, 2]})):
                (features / name).write_text(json.dumps(values))
            index = build_window_index(session)
            self.assertEqual(len(index["windows"]), 1)
            self.assertEqual(validate_window_index(index, session), [])
            (features / "audio_features.json").write_text(json.dumps({"timestamps": [0.2, 0.8], "rms": [9, 9]}))
            self.assertTrue(any("source_hash_mismatch" in issue for issue in validate_window_index(index, session)))

    def test_multimodal_artifact_validation_reports_missing_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "S1"
            session.mkdir()
            self.assertEqual(validate_multimodal_artifacts(session), ["invalid_or_missing_media_pipeline_summary"])

    def test_multimodal_artifact_validation_accepts_hashed_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "S1"
            artifact_dir = session / "processed" / "features"
            segment_dir = session / "processed" / "segments"
            artifact_dir.mkdir(parents=True)
            segment_dir.mkdir(parents=True)
            payloads = {
                "pose_landmarks": {"session_id": "S1"},
                "stable_window_index": {"windows": [{"index": 0}]},
                "acoustic_features": {"windows": [{"index": 0}]},
                "vocalization_candidates": {"training_authorized": False},
                "movement_interaction": {"training_authorized": False},
                "demuca_estimates": {
                    "training_authorized": False, "ground_truth": False,
                    "calibration_status": "not_calibrated", "estimates": [{"confidence_percent": 20}],
                },
                "multimodal_manifest": {"session_id": "S1"},
            }
            records = {}
            for name, payload in payloads.items():
                path = artifact_dir / f"{name}.json"
                path.write_text(json.dumps(payload))
                records[name] = {"path": str(path.relative_to(session)), "sha256": media._sha256_file(path)}
            summary = {"session_id": "S1", "derived_artifacts": records}
            (segment_dir / "media_pipeline_summary.json").write_text(json.dumps(summary))
            self.assertEqual(validate_multimodal_artifacts(session), [])

    def test_pipeline_summary_and_audio_artifact_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "S1"
            session.mkdir()
            windows_path = session / "processed" / "windows" / "windows.json"
            windows_path.parent.mkdir(parents=True)
            windows_path.write_text(json.dumps({"windows": []}))
            paths = []
            for name in ("pose.json", "audio.json", "vocal.json", "movement.json", "demuca.json", "manifest.json", "windows.json"):
                path = session / name
                path.write_text(json.dumps({"name": name}))
                paths.append(path)
            context = _PipelineSummaryContext(
                session_dir=session, session_id="S1", extraction={"stage": "reused"},
                segments={"segments": [], "effective_duration_seconds": 1, "max_segment_drift_seconds": 0,
                          "source_drift_seconds": 0, "trimmed_stream": None, "tail_trim_seconds": 0},
                window_seconds=1, max_tail_trim_seconds=0.2, skip_pose=False,
                pose_result={"frames_processed": 1}, pose_path=paths[0],
                audio_payload={"windows": []}, vocalization_payload={"candidate_count": 0},
                audio_path=paths[1], vocalization_path=paths[2], movement_payload={},
                movement_path=paths[3], movement_status="executed", demuca_estimates={"estimates": []},
                demuca_path=paths[4], multimodal_path=paths[5],
            )
            summary = _build_pipeline_summary(context)
            self.assertEqual(summary["session_id"], "S1")
            self.assertIn("derived_artifacts", summary)
            target = session / "stored.json"
            generated = {"source_audio_sha256": "hash", "windows": []}
            self.assertEqual(
                persist_or_reuse_audio_artifact(target, generated, source_audio_sha256="hash", overwrite=False),
                generated,
            )

    def test_media_pipeline_process_session_orchestrates_stages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = root / "dataset" / "dataset" / "sessions" / "S1" / "processed" / "segments"
            session.mkdir(parents=True)
            progress = []
            segments = {
                "session_id": "S1", "clock": "seconds", "window_seconds": 1,
                "source_drift_seconds": 0, "max_segment_drift_seconds": 0,
                "segments": [], "effective_duration_seconds": 0,
                "trimmed_stream": None, "tail_trim_seconds": 0,
            }
            with (
                patch.object(media_pipeline_module, "run_existing_extraction", return_value={"stage": "reused"}),
                patch.object(media_pipeline_module, "segment_and_synchronize", return_value=segments),
                patch.object(media_pipeline_module, "load_or_create_window_index", return_value={"windows": []}),
                patch.object(media_pipeline_module, "_process_pose_stage", return_value=(None, root / "pose.json")),
                patch.object(media_pipeline_module, "_process_audio_stage", return_value=({}, {"candidate_count": 0}, root / "audio.json", root / "vocal.json")),
                patch.object(media_pipeline_module, "_process_movement_stage", return_value=(None, root / "movement.json", "skipped_pose_not_available")),
                patch.object(media_pipeline_module, "synchronize_pose_with_segments", return_value={"segments": []}),
                patch.object(media_pipeline_module, "_build_pipeline_summary", return_value={"status": "completed"}),
                patch.object(media_pipeline_module, "validate_multimodal_artifacts", return_value=[]),
            ):
                result = media_pipeline_module.process_session(
                    "S1", root, 1, 0.2, None, True, False,
                    progress_callback=lambda stage, status: progress.append((stage, status)),
                )
            self.assertEqual(result["artifact_validation"], "passed")
            self.assertIn(("validacion", "done"), progress)

    def test_media_pipeline_rejects_stale_audio_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "audio.json"
            target.write_text(json.dumps({"source_audio_sha256": "old", "windows": []}))
            with self.assertRaisesRegex(FileExistsError, "stale audio feature output"):
                persist_or_reuse_audio_artifact(
                    target, {"windows": []}, source_audio_sha256="new", overwrite=False,
                )

    def test_window_writer_and_pipeline_graph_create_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "S1"
            segments = session / "processed" / "segments"
            features = session / "processed" / "features"
            segments.mkdir(parents=True)
            features.mkdir(parents=True)
            (segments / "video.mp4").write_bytes(b"video")
            (segments / "audio.wav").write_bytes(b"audio")
            (segments / "segments.json").write_text(json.dumps({
                "session_id": "S1", "clock": "seconds", "window_seconds": 1,
                "effective_duration_seconds": 1,
                "segments": [{"index": 0, "start_seconds": 0, "end_seconds": 1, "duration_seconds": 1,
                              "video": "video.mp4", "audio": "audio.wav", "sync_drift_seconds": 0}],
            }))
            (features / "audio_features.json").write_text(json.dumps({"timestamps": [0.5], "rms": [1]}))
            (features / "visual_motion.json").write_text(json.dumps({"timestamps": [0.5], "motion": [1]}))
            output = session / "processed" / "windows" / "windows.json"
            result = write_window_index(session, output, overwrite=False)
            self.assertEqual(result["complete_windows"], 1)
            artifacts = write_pipeline_graph(session / "graph")
            self.assertEqual({path.suffix for path in artifacts}, {".svg", ".mmd"})

    def test_pose_timestamp_and_artifact_preconditions(self):
        self.assertEqual(frame_timestamp_seconds(Path("S1_0002.jpg"), 0, 2), 0.5)
        self.assertEqual(frame_timestamp_seconds(Path("frame.jpg"), 3, 2), 1.5)
        with self.assertRaisesRegex(ValueError, "sampling_fps"):
            frame_timestamp_seconds(Path("frame.jpg"), 0, 0)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with self.assertRaisesRegex(FileNotFoundError, "model asset"):
                load_pose_landmarks(directory, "S1", directory / "missing.task", directory / "pose.json")

    def test_pose_frame_processing_serializes_landmarks(self):
        point = SimpleNamespace(x=0.1, y=0.2, z=0.3, visibility=0.9, presence=None)
        result = SimpleNamespace(
            pose_landmarks=[[point]], pose_world_landmarks=[[point]],
        )
        fake_cv2 = SimpleNamespace(imread=lambda _: object(), cvtColor=lambda image, _: image, COLOR_BGR2RGB=1)
        fake_mp = SimpleNamespace(
            ImageFormat=SimpleNamespace(SRGB="srgb"),
            Image=lambda **kwargs: kwargs,
        )
        landmarker = SimpleNamespace(detect_for_video=lambda image, timestamp: result)
        with tempfile.TemporaryDirectory() as temporary:
            frame = Path(temporary) / "S1_0002.jpg"
            frame.write_bytes(b"frame")
            record, timestamp = pose_module._process_pose_frame(
                frame, 0, 2, fake_cv2, fake_mp, landmarker, -1,
            )
        self.assertEqual(timestamp, 500)
        self.assertEqual(record["poses"][0]["landmarks"][0]["x"], 0.1)

    def test_pose_frame_processing_skips_unreadable_frame(self):
        fake_cv2 = SimpleNamespace(imread=lambda _: None)
        record, timestamp = pose_module._process_pose_frame(
            Path("missing.jpg"), 0, 1, fake_cv2, None, None, 10,
        )
        self.assertIsNone(record)
        self.assertEqual(timestamp, 10)

    def test_tracking_flattens_only_finite_report_metrics(self):
        result = flatten_metrics({
            "validation": {"micro_f1": 0.8, "exact_match_accuracy": float("nan"),
                           "per_label": {"MOVIMIENTO": {"f1": 0.7}, "bad": None}},
            "test": {"split": {"micro_f1": 0.6, "per_label": {"AUDIO": {"f1": 0.5}}}},
            "ignored": "not-a-report",
        })
        self.assertEqual(result, {
            "validation_micro_f1": 0.8, "validation_MOVIMIENTO_f1": 0.7,
            "test_split_micro_f1": 0.6, "test_split_AUDIO_f1": 0.5,
        })

    def test_media_validates_missing_extraction_and_invalid_probe_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(FileNotFoundError, "missing session metadata"):
                media.run_existing_extraction("S1", root)
            with patch.object(media, "run_command", return_value="0"):
                with self.assertRaisesRegex(ValueError, "invalid media duration"):
                    media.probe_duration(root / "video.mp4")
            with patch.object(media, "run_command", return_value=""):
                with self.assertRaisesRegex(ValueError, "could not read"):
                    media.probe_stream_duration(root / "video.mp4", "v:0")

    def test_media_stream_helpers_cover_fallback_and_concat_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "list.txt"
            media._concat_file_list([root / "a'b.mp4", root / "b.wav"], output)
            self.assertIn("a'\\''b.mp4", output.read_text())
            with patch.object(media, "run_command", return_value=json.dumps({"format": {"duration": "2"}, "streams": [{}]})):
                self.assertEqual(media._fallback_stream_duration(root / "x", "v:0"), 2)
            with patch.object(media, "run_command", return_value="audio"):
                self.assertTrue(media._has_audio_stream(root / "x"))
            with patch.object(media, "run_command", return_value='{"format":{"duration":"2"},"streams":[{},{}]}'):
                with self.assertRaisesRegex(ValueError, "could not read"):
                    media._fallback_stream_duration(root / "x", "v:0")

    def test_segment_pipeline_reuses_existing_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "S1"
            output = session / "processed" / "segments"
            output.mkdir(parents=True)
            (session / "processed" / "video").mkdir()
            (session / "processed" / "audio").mkdir()
            (session / "processed" / "video" / "S1_1280x720_10fps.mp4").write_bytes(b"video")
            (session / "processed" / "audio" / "S1_16khz_mono.wav").write_bytes(b"audio")
            manifest = {
                "session_id": "S1", "window_seconds": 1, "drift_tolerance_seconds": 0.15,
                "max_tail_trim_seconds": 0.2,
                "segments": [{"video": "window_000000/video.mp4", "audio": "window_000000/audio.wav"}],
            }
            (output / "segments.json").write_text(json.dumps(manifest))
            (output / "window_000000").mkdir()
            (output / "window_000000/video.mp4").write_bytes(b"video")
            (output / "window_000000/audio.wav").write_bytes(b"audio")
            self.assertEqual(media.segment_and_synchronize(session, "S1", window_seconds=1), manifest)

    def test_segment_synchronization_maps_modalities(self):
        manifest = {
            "session_id": "S1", "clock": "seconds", "window_seconds": 1,
            "source_drift_seconds": 0, "max_segment_drift_seconds": 0,
            "segments": [{"index": 0, "start_seconds": 0, "end_seconds": 1}],
        }
        result = synchronize_pose_with_segments(
            manifest,
            {"sampling_fps": 10, "frames": [{"timestamp_seconds": 0.5}]},
            "pose.json",
            acoustic_payload={"windows": [{"timestamp_seconds": 0.5}]},
            acoustic_features_path="audio.json",
            vocalization_payload={"candidates": [{"start_seconds": 0.2, "end_seconds": 0.8}]},
            vocalization_features_path="vocal.json",
            movement_payload={"windows": [{"window_id": "S1_W0000"}]},
            movement_features_path="movement.json",
        )
        segment = result["segments"][0]
        self.assertEqual(segment["pose_frame_indices"], [0])
        self.assertEqual(segment["acoustic_window_indices"], [0])
        self.assertEqual(segment["vocalization_candidate_indices"], [0])
        self.assertEqual(segment["movement_window_index"], 0)

    def test_audio_features_extract_complete_windows_from_stereo_wave(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "S1" / "processed" / "audio"
            session.mkdir(parents=True)
            audio_path = session / "S1_16khz_mono.wav"
            samples = np.sin(np.linspace(0, 20 * np.pi, 3200, dtype=np.float32))
            sf.write(audio_path, np.column_stack((samples, samples)), 1600)
            features, candidates = extract_audio_modalities(
                audio_path, window_seconds=1, expected_complete_windows=2
            )
            self.assertEqual(features["complete_windows"], 2)
            self.assertEqual(len(features["windows"]), 2)
            self.assertEqual(candidates["session_id"], "S1")
            self.assertFalse(candidates["training_authorized"])

    def test_media_helpers_validate_streams_and_reuse_segments(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary)
            video = session / "processed" / "video" / "S1_1280x720_10fps.mp4"
            audio = session / "processed" / "audio" / "S1_16khz_mono.wav"
            video.parent.mkdir(parents=True)
            audio.parent.mkdir(parents=True)
            video.write_bytes(b"video")
            audio.write_bytes(b"audio")
            with patch.object(media, "probe_stream_duration", side_effect=[1.0, 1.5]):
                with self.assertRaisesRegex(ValueError, "source streams differ"):
                    media._segment_source_info(video, audio, 0.2)
            self.assertEqual(media._segment_paths(session, "S1", 1, 0.1, 0.2), (video, audio))

            output = session / "segments"
            output.mkdir()
            manifest = output / "segments.json"
            payload = {"window_seconds": 1, "drift_tolerance_seconds": 0.1,
                       "max_tail_trim_seconds": 0.2,
                       "segments": [{"video": "v.mp4", "audio": "a.wav"}]}
            manifest.write_text(json.dumps(payload))
            (output / "v.mp4").write_bytes(b"v")
            (output / "a.wav").write_bytes(b"a")
            self.assertEqual(media._reuse_segments(output, manifest, 1, 0.1, 0.2), payload)

    def test_media_rejects_duplicate_movement_windows(self):
        manifest = {
            "session_id": "S1", "clock": "seconds", "window_seconds": 1,
            "source_drift_seconds": 0, "max_segment_drift_seconds": 0,
            "segments": [{"index": 0, "start_seconds": 0, "end_seconds": 1}],
        }
        with self.assertRaisesRegex(ValueError, "duplicate_movement_window"):
            synchronize_pose_with_segments(
                manifest, None, None,
                movement_payload={"windows": [{"window_id": "S1_W0000"}, {"window_id": "S1_W0000"}]},
            )
