import json
import os
import sys
import tempfile
import types
from types import SimpleNamespace
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import numpy as np
import soundfile as sf


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

from demuca_estimates import build_demuca_estimates, write_demuca_estimates
import media
import media_pipeline as media_pipeline_module
import config.management.commands.importar_laravel as laravel_command_module
import analyze_video as analyze_video_module
import multimodal_features as multimodal_features_module
import therapeutic_sessions.queries as session_queries_module
import pipeline_multimodal.views as pipeline_views_module
import pipeline_multimodal.models as pipeline_models_module
import clinical.mutations as clinical_mutations_module
import finance.mutations as finance_mutations_module
import institutions.mutations as institutions_mutations_module
import evaluations.mutations as evaluations_mutations_module
from models import MultilabelLogisticModel
from audio_features import extract_audio_modalities
from create_window_index import write_window_index
from media import synchronize_pose_with_segments
from media_pipeline import _PipelineSummaryContext, _build_pipeline_summary, persist_or_reuse_audio_artifact
from movement_interaction import build_movement_interaction_features
from pipeline_graph import write_pipeline_graph
import pose as pose_module
from pose import frame_timestamp_seconds, load_pose_landmarks
from tracking import flatten_metrics
from users.management.commands.importers.base_importer import BaseImporter
import users.management.commands.importers.session_importer as session_importer_module
from users.management.commands.importers.session_importer import SessionImporter
from users.management.commands.importers.user_importer import UserImporter
from users.management.commands.importers.patient_importer import PatientImporter
from aplicacion.servicio_analisis_video import ServicioAnalisisVideo
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

    def test_media_pipeline_stage_guards_and_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "S1"
            windows = session / "processed" / "windows"
            windows.mkdir(parents=True)
            index_path = windows / "windows.json"
            index_payload = {"windows": [{"index": 0}]}
            index_path.write_text(json.dumps(index_payload))
            with patch.object(media_pipeline_module, "validate_window_index", return_value=[]):
                self.assertEqual(media_pipeline_module.load_or_create_window_index(session, overwrite=False), index_payload)
            with patch.object(media_pipeline_module, "validate_window_index", return_value=["bad"]):
                with self.assertRaisesRegex(ValueError, "window_index_validation_failed"):
                    media_pipeline_module.load_or_create_window_index(session, overwrite=False)

            with self.assertRaisesRegex(ValueError, "provide --pose-model"):
                media_pipeline_module._process_pose_stage(session, "S1", None, False, False)
            pose, pose_path = media_pipeline_module._process_pose_stage(session, "S1", None, True, False)
            self.assertIsNone(pose)
            self.assertEqual(pose_path.name, "pose_landmarks.json")

            audio_dir = session / "processed" / "audio"
            audio_dir.mkdir(parents=True)
            (audio_dir / "S1_16khz_mono.wav").write_bytes(b"audio")
            with patch.object(media_pipeline_module, "extract_audio_modalities", return_value=({"windows": []}, {"candidate_count": 0})), \
                 patch.object(media_pipeline_module, "sha256_audio_file", return_value="hash"), \
                 patch.object(media_pipeline_module, "persist_or_reuse_audio_artifact", side_effect=lambda path, payload, **kwargs: payload):
                audio, vocal, audio_path, vocal_path = media_pipeline_module._process_audio_stage(
                    session, "S1", {"windows": []}, 1, False
                )
            self.assertEqual(audio, {"windows": []})
            self.assertEqual(vocal["candidate_count"], 0)
            self.assertEqual(audio_path.name, "acoustic_features.json")

            movement_path = session / "processed" / "features" / "movement_interaction.json"
            self.assertEqual(
                media_pipeline_module._process_movement_stage(session, None, index_payload, False)[2],
                "skipped_pose_not_available",
            )
            missing_session = Path(temporary) / "missing"
            with self.assertRaises(FileNotFoundError):
                media_pipeline_module._process_movement_stage(missing_session, {"source_frames_sha256": "x"}, index_payload, False)
            movement_path.parent.mkdir(parents=True, exist_ok=True)
            movement_path.write_text(json.dumps({"pose_source_sha256": "x", "window_index_sha256": media_pipeline_module.sha256_feature_file(index_path)}))
            reused = media_pipeline_module._process_movement_stage(session, {"source_frames_sha256": "x"}, index_payload, False)
            self.assertEqual(reused[2], "reused")

    def test_media_pipeline_executes_pose_movement_and_stale_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "S1"
            frames = session / "processed" / "frames"
            features = session / "processed" / "features"
            windows = session / "processed" / "windows"
            for directory in (frames, features, windows):
                directory.mkdir(parents=True)
            pose_path = features / "pose_landmarks.json"
            pose_path.write_text("{}")
            with patch.object(media_pipeline_module, "load_pose_landmarks", return_value={"frames_processed": 1}) as loader:
                result, path = media_pipeline_module._process_pose_stage(session, "S1", Path("pose.task"), False, False)
            self.assertEqual(result["frames_processed"], 1)
            loader.assert_called_once()

            pose_path.unlink()
            with patch.object(media_pipeline_module, "extract_pose_landmarks", return_value={"frames_processed": 2}) as extractor:
                result, _ = media_pipeline_module._process_pose_stage(session, "S1", Path("pose.task"), False, True)
            self.assertEqual(result["frames_processed"], 2)
            extractor.assert_called_once()

            index_path = windows / "windows.json"
            index_path.write_text(json.dumps({"windows": []}))
            pose_result = {"frames": [], "source_frames_sha256": "pose"}
            with patch.object(media_pipeline_module, "build_movement_interaction_features", return_value={"frames": []}) as builder:
                payload, path, status = media_pipeline_module._process_movement_stage(session, pose_result, {"windows": []}, True)
            self.assertEqual(status, "executed")
            self.assertEqual(payload, {"frames": []})
            builder.assert_called_once()

            self.assertTrue(media_pipeline_module._audio_artifact_is_stale(
                {"source_audio_sha256": "old"}, {}, "new", None, None,
            ))
            self.assertTrue(media_pipeline_module._audio_artifact_is_stale(
                {"source_audio_sha256": "new", "window_seconds": "bad"}, {}, "new", 1, None,
            ))
            self.assertTrue(media_pipeline_module._audio_artifact_is_stale(
                {"source_audio_sha256": "new", "windows": []}, {"candidates": []}, "new", None, 1,
            ))

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

    def test_pose_extraction_writes_payload_and_loads_matching_artifact(self):
        point = SimpleNamespace(x=0.1, y=0.2, z=0.3, visibility=0.9, presence=0.8)
        detection = SimpleNamespace(pose_landmarks=[[point]], pose_world_landmarks=[])

        class FakeLandmarker:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def detect_for_video(self, image, timestamp):
                return detection

        fake_cv2 = types.ModuleType("cv2")
        fake_cv2.COLOR_BGR2RGB = 1
        fake_cv2.imread = lambda _: object()
        fake_cv2.cvtColor = lambda image, _: image
        fake_mp = types.ModuleType("mediapipe")
        fake_mp.ImageFormat = SimpleNamespace(SRGB="SRGB")
        fake_mp.Image = lambda **kwargs: kwargs
        fake_mp.tasks = SimpleNamespace(
            BaseOptions=lambda **kwargs: kwargs,
            vision=SimpleNamespace(
                RunningMode=SimpleNamespace(VIDEO="VIDEO"),
                PoseLandmarkerOptions=lambda **kwargs: kwargs,
                PoseLandmarker=SimpleNamespace(create_from_options=lambda options: FakeLandmarker()),
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frames = root / "frames"
            frames.mkdir()
            (frames / "S1_0001.jpg").write_bytes(b"one")
            (frames / "S1_0002.jpg").write_bytes(b"two")
            model = root / "pose.task"
            model.write_bytes(b"model")
            output = root / "features" / "pose.json"
            with patch.dict(sys.modules, {"cv2": fake_cv2, "mediapipe": fake_mp}):
                payload = pose_module.extract_pose_landmarks(frames, "S1", model, output)
            self.assertEqual(payload["frames_processed"], 2)
            self.assertEqual(payload["frames"][0]["poses"][0]["world_landmarks"], [])
            self.assertEqual(pose_module.load_pose_landmarks(frames, "S1", model, output), payload)
            payload["num_poses"] = 2
            output.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "configuration_mismatch"):
                pose_module.load_pose_landmarks(frames, "S1", model, output, num_poses=4)

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

    def test_importer_base_normalizes_legacy_values(self):
        importer = BaseImporter()
        self.assertEqual(importer._clean_text(" <p>Hola&nbsp;</p><br> mundo "), "Hola\nmundo")
        self.assertEqual(importer._clean_text("null"), "")
        self.assertEqual(importer._to_int("12.8"), 12)
        self.assertEqual(importer._to_int("bad", 7), 7)
        self.assertEqual(str(importer._to_decimal("12,50")), "12.50")
        self.assertIsNone(importer._to_date("2026-99-99"))
        self.assertIsNotNone(importer._to_date("31/12/2026"))
        self.assertIsNotNone(importer._to_datetime("2026-01-02 03:04:05"))
        self.assertEqual(importer._limit_text("abcdef", 3), "abc")
        self.assertEqual(importer._normalize_name("  Ana   Pérez "), "ana pérez")

    def test_user_importer_validates_rows_and_dry_runs_users(self):
        messages = []
        importer = UserImporter(logger=messages.append, dry_run=True)
        self.assertEqual(importer.import_users([["1"]]), {})
        self.assertEqual(importer.stats["skipped"], 1)
        invalid = ["bad", "Ana", "Pérez", "", "123", "", "", "", "", "", "", ""]
        importer.import_users([invalid])
        self.assertEqual(importer.stats["skipped"], 1)
        row = ["10", "<b>Ana</b>", "Pérez", "", "+54 (11) 123", "", "0", "public"]
        with patch.object(importer, "_create_or_update_user", return_value=SimpleNamespace(username="legacy_10")):
            users = importer.import_users([row])
        self.assertEqual(list(users), ["ana pérez"])
        self.assertEqual(importer._clean_and_validate_phone("+54 (11)", 20), "+5411")
        self.assertEqual(importer._clean_and_validate_ci("0", 20, 10), "LEGACY-USR-10")
        self.assertEqual(importer._normalize_value("unknown", {"known": "x"}, "default"), "default")
        self.assertTrue(any("RESUMEN" in message for message in messages))

    def test_user_importer_maps_existing_users_and_collision_names(self):
        importer = UserImporter(dry_run=True)
        importer._cache_groups = {"therapist": None}
        with patch("users.management.commands.importers.user_importer.User") as user_model:
            user_model.objects.filter.return_value.exists.side_effect = [True, False, True]
            self.assertEqual(importer._generate_unique_username(4), "legacy_user_4_1")
            self.assertIn("@legacy.com", importer._generate_email("Ana", "Pérez", 4))
        self.assertEqual(importer._clean_and_validate_name("Ana!", 20), "Ana")
        self.assertEqual(importer._clean_and_validate_name(None, 20), "")
        self.assertEqual(importer._clean_and_validate_ci("999999", 20, 4), "LEGACY-USR-4")

    def test_user_importer_processes_long_row_and_progress_logging(self):
        messages = []
        importer = UserImporter(logger=messages.append, dry_run=True)
        row = ["11", "Ana", "Lopez", "", "123", "", "456", "public", "inactive", "foto.jpg", "2026-01-01", ""]
        with patch.object(importer, "_create_or_update_user", return_value=SimpleNamespace()):
            importer.import_users([row] * 50)
        self.assertTrue(any("50/50" in message for message in messages))

    def test_session_importer_maps_statuses_and_skips_missing_payments(self):
        importer = SessionImporter(logger=lambda _: None, dry_run=True)
        self.assertEqual(importer._map_session_status("PENDIENTE").value, "agendada")
        self.assertEqual(importer._map_session_status("CONFIRMADO").value, "confirma")
        self.assertEqual(importer._map_session_status("REPROGRAMADO").value, "reprograma")
        self.assertEqual(importer._map_session_status("CANCELADO").value, "cancelada")
        self.assertEqual(importer._map_session_payment_status("PAGADO").value, "paid")
        self.assertEqual(importer._map_session_payment_status("PRESTADO").value, "exempt")
        self.assertEqual(importer._map_session_payment_status("otro").value, "pending")
        row = ["1", "999", "1", "1", "REALIZADO", "2026-01-02", "PAGADO", "", "", "", "", "2026-01-02"]
        self.assertEqual(importer._process_row(row, {}, SimpleNamespace()), "no_payment")

    def test_session_importer_dry_run_counts_evaluations(self):
        importer = SessionImporter(logger=lambda _: None, dry_run=True)
        payment = SimpleNamespace(patient=SimpleNamespace())
        row = ["1", "10", "2", "3", "REALIZADO", "2026-01-02", "PAGADO", "Bueno", "Regular", "Ejercicio", "Nota", "2026-01-02 10:00:00"]
        importer._cache_scale_values = {}
        fake_session_model = MagicMock(return_value=SimpleNamespace())
        fake_session_model.SessionStatus = session_importer_module.Session.SessionStatus
        fake_session_model.PaymentStatus = session_importer_module.Session.PaymentStatus
        with patch.object(session_importer_module, "Session", fake_session_model):
            importer._process_row(row, {10: payment}, SimpleNamespace())
        self.assertEqual(importer.stats, {"sessions": 1, "evaluations": 2})

    def test_session_importer_loads_scale_cache_and_links_matching_response(self):
        importer = SessionImporter(logger=lambda _: None)
        scale_value = SimpleNamespace(scale_id=2, label="1: Excelente")
        with patch.object(session_importer_module.ScaleValue.objects, "filter", return_value=[scale_value]):
            cache = importer._load_scale_values()
        importer._cache_scale_values = cache
        self.assertIn((2, "excelente"), cache)
        fake_evaluation = SimpleNamespace()
        with patch.object(session_importer_module.ScaleEvaluation.objects, "create", return_value=fake_evaluation) as create_evaluation, \
             patch.object(session_importer_module.ScaleEvaluationValueResponse.objects, "create") as create_response:
            importer._create_evaluation_response(
                SimpleNamespace(patient=SimpleNamespace(), therapist=SimpleNamespace()),
                2, "Excelente", None,
            )
        create_evaluation.assert_called_once()
        create_response.assert_called_once_with(evaluation=fake_evaluation, scale_value=scale_value)

    def test_session_importer_reports_short_and_unpaid_rows(self):
        messages = []
        importer = SessionImporter(logger=messages.append, dry_run=True)
        rows = [["1"], ["1", "99", "1", "1", "REALIZADO", "2026-01-01", "PAGADO", "", "", "", "", ""]]
        importer.import_sessions(rows, {}, SimpleNamespace())
        self.assertEqual(importer.stats["sessions"], 0)
        self.assertTrue(any("insuficientes" in message for message in messages))
        self.assertTrue(any("payment no encontrado" in message for message in messages))

    def test_laravel_command_parses_remote_rows_and_safe_tables(self):
        command = laravel_command_module.Command()
        self.assertEqual(command._remote_columns("usuarios")[0], "id")
        with self.assertRaisesRegex(Exception, "Tabla no permitida"):
            command._remote_columns("drop_table")
        cursor = MagicMock()
        cursor.fetchall.return_value = [{"id": 1, "nombre": "Ana"}]
        connection = MagicMock()
        connection.cursor.return_value = cursor
        rows = command._query_remote_mysql(connection, "usuarios", ["id", "nombre"])
        self.assertEqual(rows[0][0], "1")
        cursor.execute.assert_called_once()

        process = SimpleNamespace(returncode=0, stdout="1\tAna\n", stderr="")
        with patch.object(laravel_command_module.subprocess, "run", return_value=process):
            ssh_rows = command._query_remote_ssh(
                {"user": "u", "password": "p", "database": "d", "host": "h"},
                "usuarios", ["id", "nombre"],
            )
        self.assertEqual(ssh_rows, [["1", "Ana"]])
        with patch.object(laravel_command_module.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout="", stderr="failed")):
            with self.assertRaisesRegex(Exception, "SSH/mysql remoto falló"):
                command._query_remote_ssh({"user": "u", "password": "p", "database": "d", "host": "h"}, "usuarios", ["id"])

    def test_laravel_command_imports_users_patients_payments_and_sessions(self):
        command = laravel_command_module.Command()
        fake_user = MagicMock(id=7)
        fake_patient = MagicMock(id=8, diagnosis="", residence="", notes="")
        fake_payment = MagicMock(patient=fake_patient)
        user_model = MagicMock()
        user_model.objects.update_or_create.return_value = (fake_user, True)
        patient_model = MagicMock()
        patient_model.objects.update_or_create.return_value = (fake_patient, True)
        payment_model = MagicMock()
        payment_model.objects.create.return_value = fake_payment
        payment_model.PaymentStatus = SimpleNamespace(COMPLETED="completed", PENDING="pending", PARTIAL="partial")
        payment_model.PaymentMethod = SimpleNamespace(QR="qr", CASH="cash")
        session_model = MagicMock()
        session_model.objects.create.return_value = MagicMock()
        session_model.SessionType = SimpleNamespace(INDIVIDUAL="individual")
        session_model.SessionStatus = SimpleNamespace(AGENDADA="agendada", COMPLETADA="completada", CONFIRMADA="confirma", REPROGRAMA="reprograma", CANCELADA="cancelada")
        session_model.PaymentStatus = SimpleNamespace(PAID="paid", EXEMPT="exempt", PENDING="pending")
        with patch.object(laravel_command_module, "User", user_model), \
             patch.object(laravel_command_module, "Patient", patient_model), \
             patch.object(laravel_command_module, "Payment", payment_model), \
             patch.object(laravel_command_module, "Session", session_model):
            users = command._import_users([["1", "Ana", "Lopez", "", "", "123", "", "CI", "", "activo", "", "", "", "visible", "", ""]])
            patients, info = command._import_patients_and_info([], [], users, fake_user)
            payments = command._import_payments(
                [["10", "20", "100", "", "100", "", "", "", "", "", ""]],
                {20: {"patient": fake_patient}}, {10: "proof.pdf"}, {10: 2},
            )
            command._import_sessions(
                [["1", "10", "1", "1", "REALIZADO", "2026-01-01", "PAGADO", "ERI", "CIM", "", "", "", ""]],
                payments, fake_user,
            )
        self.assertIn("ana lopez", users)
        self.assertIn(10, payments)
        payment_model.objects.create.assert_called_once()
        session_model.objects.create.assert_called_once()

    def test_laravel_command_helpers_cover_notes_proofs_and_cycles(self):
        command = laravel_command_module.Command()
        self.assertEqual(command._extract_payment_proofs([["", "3", "", "", "", "proof", "", "", "", ""]]), {3: "proof"})
        self.assertEqual(command._count_cycles_by_payment([["", "3"] * 7 + ["", "", "", "", "", ""]]), {3: 1})
        with patch.object(laravel_command_module, "Patient", SimpleNamespace(Status=SimpleNamespace(ACTIVE="active", PENDING="pending"))):
            self.assertEqual(command._map_patient_status("activo"), "active")
            self.assertEqual(command._map_patient_status("otro"), "pending")
        note = MagicMock(content="old")
        with patch.object(laravel_command_module.PatientClinicalNote.objects, "get_or_create", return_value=(note, False)):
            command._upsert_clinical_note(MagicMock(), MagicMock(), "GENERAL", "new")
        note.save.assert_called_once()
        self.assertEqual(command._split_name("Ana María López"), ("Ana", "María López"))

    def test_laravel_command_runs_dry_etl_and_connection_lifecycle(self):
        command = laravel_command_module.Command()
        datasets = {name: [] for name in (
            "usuarios", "clientes", "infoclientes", "pagos", "archivospagos", "ciclos",
            "plandeintervencions", "subplandeintervencions", "matrizescalas", "submatrizescalas", "demucas",
        )}
        therapist = SimpleNamespace(id=1)
        with patch.object(command, "_truncate_imported_data"), \
             patch.object(command, "_ensure_default_therapist", return_value=therapist), \
             patch.object(command, "_import_users", return_value={}), \
             patch.object(command, "_import_patients_and_info", return_value=({}, {})), \
             patch.object(command, "_extract_payment_proofs", return_value={}), \
             patch.object(command, "_count_cycles_by_payment", return_value={}), \
             patch.object(command, "_import_payments", return_value={}), \
             patch.object(command, "_import_sessions"), \
             patch.object(command, "_import_intervention_plans"), \
             patch.object(command, "_import_scales_and_evaluations"), \
             patch.object(laravel_command_module.transaction, "atomic") as atomic, \
             patch.object(laravel_command_module.transaction, "set_rollback") as rollback:
            atomic.return_value.__enter__.return_value = None
            command._run_legacy_etl(datasets, {"dry_run": True, "truncate": True})
        rollback.assert_called_once_with(True)

        connection = MagicMock()
        with patch.object(command, "_open_legacy_connection", return_value=(connection, None)), \
             patch.object(command, "_fetch_legacy_datasets", return_value=datasets) as fetch, \
             patch.object(command, "_close_legacy_resources") as close:
            self.assertEqual(command._load_legacy_datasets({"host": "h", "user": "u", "password": "p", "database": "d", "port": 3306}), datasets)
        fetch.assert_called_once_with(connection)
        close.assert_called_once_with(connection, None)

    def test_laravel_command_covers_plans_scales_and_score_mapping(self):
        command = laravel_command_module.Command()
        self.assertEqual(command._score_from_legacy("", "3", 2), 2)
        self.assertEqual(command._score_from_legacy("MUCHO", "", 5), 4)
        self.assertEqual(command._score_from_legacy("9", "", 5), 5)
        self.assertEqual(command._score_from_legacy("unknown", "", 5), 0)
        self.assertEqual(command._append_text("a", "b"), "a | b")
        self.assertEqual(command._append_text("a", "a"), "a")
        self.assertEqual(command._map_plan_moment("cierre").value, "DESPEDIDA")
        self.assertEqual(command._map_plan_moment("otro").value, "BIENVENIDA")

        fake_plan = MagicMock(id=10)
        fake_step = MagicMock(musical_resources="")
        intervention_model = MagicMock()
        intervention_model.objects.create.return_value = fake_plan
        planstep_model = MagicMock()
        planstep_model.objects.create.return_value = fake_step
        planstep_model.Moment = laravel_command_module.PlanStep.Moment
        patient = SimpleNamespace(id=1)
        plan_by_patient = {}
        step_by_plan = {}
        row = ["99", "1", "2", "inicio", "Objetivo", "Foco", "Metodo", "Enfoque", "30", "", "", ""]
        with patch.object(laravel_command_module, "InterventionPlan", intervention_model), patch.object(laravel_command_module, "PlanStep", planstep_model):
            self.assertTrue(command._import_plan_row(row, plan_by_patient, step_by_plan, {2: {"patient": patient}}, SimpleNamespace()))
            command._apply_subplan_row(["", "99", "RECURSO", "Tambor", "", ""], step_by_plan)
        self.assertEqual(step_by_plan[99], fake_step)
        fake_step.save.assert_called_once()

        scale = MagicMock()
        scale_model = MagicMock()
        scale_model.objects.get_or_create.return_value = (scale, True)
        scale_model.ScaleType = laravel_command_module.Scale.ScaleType
        subscale_model = MagicMock()
        subscale_model.objects.get_or_create.return_value = (MagicMock(max_value=5), True)
        with patch.object(laravel_command_module, "Scale", scale_model), patch.object(laravel_command_module, "Subscale", subscale_model):
            scales, mapping = {}, {}
            command._import_matrix_row(["1", "CAT", "SUB", "5", "", "", ""], scales, mapping)
            command._import_submatrix_row(["", "1", "", "SUB2", "", ""], scales, mapping)
        self.assertIn("CAT", scales)
        self.assertEqual(mapping[1], "CAT")

    def test_multimodal_features_aggregate_acoustic_and_interaction_windows(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "S1"
            features = session / "processed" / "features"
            features.mkdir(parents=True)
            (features / "acoustic_features.json").write_text(json.dumps({
                "windows": [
                    {"timestamp_seconds": 0.2, "spectral_centroid_hz": 100, "pitch_median_hz": 200},
                    {"timestamp_seconds": 0.8, "spectral_centroid_hz": 300, "pitch_median_hz": None},
                ]
            }))
            (features / "movement_interaction.json").write_text(json.dumps({
                "windows": [{"window_id": "S1_W0000", "pose_count_mean": 1, "pose_count_max": 2}]
            }))
            result = multimodal_features_module.derived_multimodal_features(session, window_seconds=1)
        self.assertEqual(result["_W0000"]["acoustic_spectral_centroid_mean"], 200)
        self.assertEqual(result["_W0000"]["acoustic_pitch_median_mean"], 200)
        self.assertEqual(result["_W0000"]["pose_count_max"], 2)

    def test_patient_importer_dry_run_handles_placeholder_and_duplicate_ci(self):
        messages = []
        importer = PatientImporter(logger=messages.append, dry_run=True)
        row = ["1", "Ana", "Lopez", "0", "2020-01-01", "", "note", "diag", "res", "Tutor", "", "", "objective", "social", "cognitive", "physical", "emotional", "method", "additional", "5", "2026-01-01 10:00:00"]
        duplicate_row = row.copy()
        duplicate_row[3] = "ABC"
        patients, info = importer.import_patients([row, duplicate_row, duplicate_row], {}, SimpleNamespace())
        self.assertEqual(len(patients), 1)
        self.assertEqual(importer.stats["patients"], 3)
        self.assertEqual(importer._split_name(""), ("Tutor", "Legacy"))
        self.assertTrue(any("CI duplicado" in message for message in messages))
        self.assertEqual(importer._resolve_patient_ci("0000", 9, "A", "B"), "LEGACY-PAT-9")

    def test_analyze_video_adapter_and_progress_reporter(self):
        reporter = analyze_video_module.ProgressReporter(enabled=True)
        reporter("extraccion", "start")
        reporter("extraccion", "done")
        reporter("unknown", "start")
        disabled = analyze_video_module.ProgressReporter(enabled=False)
        disabled("audio", "start")
        fake_service = MagicMock()
        fake_service.ejecutar.return_value = {"status": "completed"}
        with patch.object(analyze_video_module, "ServicioAnalisisVideo", return_value=fake_service):
            result = analyze_video_module.analyze_video(Path("video.mp4"), session_id="S1")
        self.assertEqual(result["status"], "completed")
        fake_service.ejecutar.assert_called_once()

    def test_service_writes_metadata_and_reuses_staged_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = root / "S1"
            staged = session / "raw" / "input.mp4"
            staged.parent.mkdir(parents=True)
            staged.write_bytes(b"video")
            manifest = session / "session_manifest.json"
            repository = ServicioAnalisisVideo.__dict__["_write_session_metadata"]
            from infraestructura.persistencia_json import RepositorioArtefactos
            repo = RepositorioArtefactos()
            repository(session, staged, manifest, "S1", 2.5, repo)
            self.assertEqual(json.loads(manifest.read_text())["duration_seconds"], 2.5)
            service = ServicioAnalisisVideo(lambda _: 1, lambda *args, **kwargs: {})
            self.assertEqual(service._reuse_or_stage(session, session / "response.json", staged, manifest, staged, repo.huella(staged), repo), 2.5)

    def test_service_executes_pipeline_and_returns_safe_response_without_mlflow(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "input.mp4"
            video.write_bytes(b"video")
            session_dir = root / "dataset" / "dataset" / "sessions" / "S1"
            session_dir.mkdir(parents=True)
            response_path = session_dir / "processed" / "analysis_response.json"
            repository = MagicMock()
            repository.leer_json.side_effect = lambda path: json.loads(path.read_text())
            summary = {
                "status": "completed", "segments_created": 1, "pose_enabled": False,
                "pose_frames_processed": 0, "acoustic_windows": 1,
                "vocalization_candidates": 0, "movement_interaction_status": "skipped",
                "artifact_validation": "passed", "max_segment_drift_seconds": 0,
                "source_drift_seconds": 0, "tail_trim_seconds": 0,
            }
            service = ServicioAnalisisVideo(lambda _: 1.5, MagicMock(return_value=summary))
            with patch.object(service, "_prepare_session", return_value=(
                session_dir, root / "pose.task", True, response_path, repository, "a" * 64, 1.5,
            )), patch("aplicacion.servicio_analisis_video.write_demuca_draft", return_value={"draft": True}), \
                 patch("aplicacion.servicio_analisis_video.predict_session", return_value={"status": "unavailable", "training_authorized": False}), \
                 patch("aplicacion.servicio_analisis_video.log_run", side_effect=RuntimeError("mlflow missing")):
                result = service.ejecutar(
                    video, session_id="S1", project_root=root, window_seconds=1,
                    max_tail_trim_seconds=0.2, pose_model=None, skip_pose=True,
                    session_id_pattern=analyze_video_module.SESSION_ID_PATTERN,
                )
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["demuca"]["status"], "draft")
            self.assertEqual(result["mlflow"]["status"], "unavailable")
            repository.escribir_json_atomico.assert_called_once()

    def test_multilabel_model_trains_predicts_and_restores_artifact(self):
        rows = [
            {"audio_rms_mean": 0, "audio_zcr_mean": 0, "visual_motion_mean": 0, "visual_motion_max": 0, "sound": 0, "movement": 1},
            {"audio_rms_mean": 1, "audio_zcr_mean": 1, "visual_motion_mean": 1, "visual_motion_max": 1, "sound": 1, "movement": 1},
            {"audio_rms_mean": 2, "audio_zcr_mean": 2, "visual_motion_mean": 2, "visual_motion_max": 2, "sound": 1, "movement": 0},
        ]
        model = MultilabelLogisticModel().fit(rows, ["sound", "movement"])
        probabilities = model.predict_proba(rows)
        self.assertEqual(len(probabilities), 3)
        self.assertEqual(len(model.predict(rows)), 3)
        restored = MultilabelLogisticModel.from_dict(model.to_dict())
        self.assertEqual(restored.predict(rows), model.predict(rows))
        constant = MultilabelLogisticModel().fit(rows, ["sound"])
        self.assertIn("sound", constant.predict_proba(rows)[0])
        with self.assertRaisesRegex(ValueError, "invalid_or_missing_model_feature"):
            model.predict([{"audio_rms_mean": 1}])
        with self.assertRaisesRegex(ValueError, "unsupported_model_type"):
            MultilabelLogisticModel.from_dict({"model_type": "other"})

    def test_session_query_helpers_group_cycles_and_apply_filters(self):
        patient = SimpleNamespace(first_name="Ana", last_name="Uno")
        sessions = [
            SimpleNamespace(patient_id=1, cycle_number=2, therapist_id=4, therapist="T", patient=patient,
                            payment_status="paid", session_status="completa", session_date="2026-01-02"),
            SimpleNamespace(patient_id=1, cycle_number=2, therapist_id=4, therapist="T", patient=patient,
                            payment_status="pending", session_status="agendada", session_date="2026-01-03"),
        ]
        queryset = MagicMock()
        queryset.select_related.return_value = queryset
        queryset.prefetch_related.return_value = queryset
        queryset.order_by.return_value = queryset
        queryset.exists.return_value = True
        queryset.__iter__.return_value = iter(sessions)
        cycles = session_queries_module._build_cycles(queryset)
        self.assertEqual(cycles[0].session_count, 2)
        self.assertEqual(cycles[0].payment_summary.paid, 1)
        self.assertEqual(cycles[0].status, "Activo")

        user = SimpleNamespace(is_staff=False, is_superuser=False, pk=4)
        self.assertEqual(session_queries_module._restrict_to_user(user, None), "4")
        with self.assertRaisesRegex(Exception, "No autorizado"):
            session_queries_module._restrict_to_user(user, "999")
        filtered = MagicMock()
        filtered.filter.return_value = filtered
        result = session_queries_module._apply_session_filters(
            filtered, "1", "4", "individual", "paid", "completa", "Ana",
            "2026-01-01", "2026-01-31", True,
        )
        self.assertIs(result, filtered)
        self.assertGreaterEqual(filtered.filter.call_count, 5)

    def test_pipeline_view_helpers_validate_payloads_and_lineage(self):
        request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False), headers={})
        self.assertFalse(pipeline_views_module._authenticate_request(request))
        with self.assertRaisesRegex(Exception, "invalid_json"):
            pipeline_views_module._json_body(SimpleNamespace(body=b"{"))
        with self.assertRaisesRegex(Exception, "json_object_required"):
            pipeline_views_module._json_body(SimpleNamespace(body=b"[]"))
        self.assertEqual(pipeline_views_module._mlops_lineage(None), {})
        with tempfile.TemporaryDirectory() as temporary:
            model = Path(temporary) / "model.json"
            model.write_text("model")
            with patch.object(pipeline_views_module, "_safe_model_path", return_value=model):
                lineage = pipeline_views_module._mlops_lineage({
                    "dataset_hash": "data", "mlflow": {"run_id": "r", "experiment": "e"},
                    "model_predictions": {"model_path": str(model), "model_type": "demo", "model_version": "1"},
                })
        self.assertEqual(lineage["mlflow_run_id"], "r")
        self.assertEqual(len(lineage["model_sha256"]), 64)
        sample = SimpleNamespace(
            id=1, session_id="S1", window_id="W1", features={}, labels={}, reviewed=False,
            start_time=0, end_time=1, demuca_phase="", sound_tags=[], movement_tags=[],
            interaction_tags=[], derived_features={}, pose_landmarks=[], artifact_payload={},
            updated_at=SimpleNamespace(isoformat=lambda: "now"),
        )
        self.assertFalse(pipeline_views_module._sample_payload(sample)["training_authorized"])
        with self.assertRaisesRegex(Exception, "annotation window fields"):
            pipeline_views_module._annotation_values({})

    def test_clinical_mutation_helpers_resolve_tutors_and_sessions(self):
        self.assertEqual(clinical_mutations_module._generate_username("Lopez", "123"), "lopez_123")
        self.assertTrue(clinical_mutations_module._generate_password("Lopez", "123"))
        user_filter = MagicMock()
        user_filter.first.return_value = None
        user_filter.exists.return_value = False
        with patch.object(clinical_mutations_module.User.objects, "filter", return_value=user_filter):
            with patch.object(clinical_mutations_module.User.objects, "create", return_value=SimpleNamespace(id=1)) as create:
                tutor, username, password, created = clinical_mutations_module._resolve_tutor("Ana Lopez", "", "123", "", "Lopez")
        self.assertTrue(created)
        self.assertTrue(username.startswith("lopez_"))
        create.assert_called_once()
        patient = SimpleNamespace(id=1)
        fake_session = MagicMock()
        with patch.object(clinical_mutations_module, "Session", fake_session), \
             patch.object(fake_session.objects, "bulk_create") as bulk:
            clinical_mutations_module._create_initial_sessions(patient, 2, "monday", "10:30")
        self.assertEqual(len(bulk.call_args.args[0]), 4)

    def test_analyze_video_main_handles_success_failure_and_service_input(self):
        with patch.object(analyze_video_module, "analyze_video", return_value={"status": "completed"}), \
             patch.object(analyze_video_module.sys, "argv", ["analyze_video.py", "video.mp4", "--session-id", "S1", "--no-progress"]):
            self.assertEqual(analyze_video_module.main(), 0)
        with patch.object(analyze_video_module, "analyze_video", side_effect=ValueError("bad")), \
             patch.object(analyze_video_module.sys, "argv", ["analyze_video.py", "video.mp4", "--session-id", "S1", "--no-progress"]):
            self.assertEqual(analyze_video_module.main(), 2)
        with patch.dict(os.environ, {"PIPELINE_INPUT_PATH": "service.mp4", "PIPELINE_SESSION_ID": "S2"}), \
             patch.object(analyze_video_module, "analyze_video", return_value={"status": "completed"}), \
             patch.object(analyze_video_module.sys, "argv", ["analyze_video.py", "--service-input", "--no-progress"]):
            self.assertEqual(analyze_video_module.main(), 0)

    def test_tracking_logs_finite_metrics_and_artifacts(self):
        class Run:
            info = SimpleNamespace(run_id="run-1")

        class Mlflow:
            def __init__(self):
                self.logged = []
            def set_tracking_uri(self, value): self.logged.append(("uri", value))
            def get_experiment_by_name(self, value): return None
            def create_experiment(self, *args, **kwargs): return "exp"
            def set_experiment(self, value): self.logged.append(("experiment", value))
            def start_run(self, run_name):
                self.logged.append(("run", run_name))
                return self
            def __enter__(self): return Run()
            def __exit__(self, *args): return False
            def log_params(self, value): self.logged.append(("params", value))
            def log_metrics(self, value): self.logged.append(("metrics", value))
            def set_tags(self, value): self.logged.append(("tags", value))
            def log_artifact(self, value): self.logged.append(("artifact", value))

        import tracking as tracking_module
        fake_mlflow = Mlflow()
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "artifact.json"
            artifact.write_text("{}")
            with patch.dict(sys.modules, {"mlflow": fake_mlflow}):
                run_id = tracking_module.log_run(
                    experiment_name="exp", run_name="run", params={"p": 1},
                    metrics={"good": 1, "bad": float("nan")}, tags={"tag": "x"},
                    artifacts=[artifact], project_root=Path(temporary),
                )
        self.assertEqual(run_id, "run-1")
        self.assertTrue(any(kind == "metrics" for kind, _ in fake_mlflow.logged))

    def test_media_segment_pipeline_executes_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "S1"
            video = session / "processed" / "video" / "S1_1280x720_10fps.mp4"
            audio = session / "processed" / "audio" / "S1_16khz_mono.wav"
            video.parent.mkdir(parents=True)
            audio.parent.mkdir(parents=True)
            video.write_bytes(b"v")
            audio.write_bytes(b"a")
            manifest = {"session_id": "S1", "segments": [{"index": 0}]}
            with patch.object(media, "_segment_source_info", return_value=(1.0, 1.0, 0.0, None, 1.0)), \
                 patch.object(media, "_build_segments", return_value=([{"index": 0}], 0.0)), \
                 patch.object(media, "_segment_manifest", return_value=manifest), \
                 patch.object(media, "_write_segment_manifest") as writer:
                result = media.segment_and_synchronize(session, "S1", window_seconds=1)
            self.assertEqual(result, manifest)
            writer.assert_called_once()

    def test_media_validation_and_reuse_helpers_cover_edge_cases(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            media._segment_paths(Path("/tmp"), "S1", 0, 0.1, 0.2)
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary)
            with self.assertRaises(FileNotFoundError):
                media._segment_paths(session, "S1", 1, 0.1, 0.2)
            output = session / "segments"
            output.mkdir()
            manifest_path = output / "segments.json"
            manifest_path.write_text(json.dumps({
                "window_seconds": 1, "drift_tolerance_seconds": 0.1,
                "max_tail_trim_seconds": 0.2, "segments": [],
            }))
            self.assertIsNotNone(media._reuse_segments(output, manifest_path, 1, 0.1, 0.2))
            self.assertIsNone(media._reuse_segments(output, manifest_path, 2, 0.1, 0.2))
            list_file = session / "list.txt"
            media._concat_file_list([Path("a'b.mp4")], list_file)
            self.assertIn("file 'a'\\''b.mp4'", list_file.read_text())
            with patch.object(media, "probe_stream_duration", side_effect=[2.0, 2.1]):
                self.assertEqual(media._segment_source_info(Path("v"), Path("a"), 0.2)[3], "audio")
            with patch.object(media, "probe_stream_duration", side_effect=[2.1, 2.0]):
                self.assertEqual(media._segment_source_info(Path("v"), Path("a"), 0.2)[3], "video")

    def test_pipeline_dataset_endpoints_and_annotation_validation(self):
        user = SimpleNamespace(is_authenticated=True, is_staff=True)
        request = SimpleNamespace(user=user, method="GET", headers={}, body=b"")
        dataset = SimpleNamespace(
            id=1, name="D", description="", status="draft", training_authorized=False,
            authorized_at=None, created_at=SimpleNamespace(isoformat=lambda: "c"),
            updated_at=SimpleNamespace(isoformat=lambda: "u"),
        )
        samples = MagicMock()
        samples.all.return_value = samples
        samples.count.return_value = 0
        samples.filter.return_value.count.return_value = 0
        dataset.samples = samples
        queryset = MagicMock()
        queryset.__iter__.return_value = iter([dataset])
        with patch.object(pipeline_views_module.TherapistDataset.objects, "all", return_value=queryset):
            response = pipeline_views_module.datasets(request)
        self.assertEqual(response.status_code, 200)
        request.method = "POST"
        request.body = json.dumps({"name": " New ", "description": "desc"}).encode()
        with patch.object(pipeline_views_module.TherapistDataset.objects, "create", return_value=dataset) as create:
            response = pipeline_views_module.datasets(request)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(create.call_args.kwargs["name"], "New")
        features = {name: 1.0 for name in pipeline_models_module.DATASET_FEATURE_COLUMNS}
        self.assertEqual(pipeline_models_module.validate_dataset_values(features, {"visual__MOVIMIENTO": 1}), None)
        with self.assertRaisesRegex(Exception, "features"):
            pipeline_models_module.validate_dataset_values({}, {"y": 1})

    def test_session_query_pagination_resolvers_cover_normal_and_cycle_paths(self):
        query = session_queries_module.Query()
        info = SimpleNamespace(context=SimpleNamespace(user=SimpleNamespace(
            is_staff=True, is_superuser=False, is_authenticated=True, pk=7,
        )))
        queryset = MagicMock()
        queryset.__getitem__.return_value = [SimpleNamespace(id=1)]
        queryset.count.return_value = 3
        queryset.filter.return_value = queryset
        ordered = MagicMock()
        ordered.filter.return_value = queryset
        ordered.count.return_value = 3
        ordered.__getitem__.return_value = [SimpleNamespace(id=1)]
        with patch.object(session_queries_module.Session.objects, "select_related", return_value=MagicMock(order_by=MagicMock(return_value=ordered))), \
             patch.object(session_queries_module, "_apply_session_filters", return_value=ordered):
            normal = query.resolve_sessions(info, page=2, page_size=2)
        self.assertEqual(normal.total_count, 3)
        with patch.object(session_queries_module.Session.objects, "select_related", return_value=MagicMock(order_by=MagicMock(return_value=ordered))), \
             patch.object(session_queries_module, "_apply_session_filters", return_value=ordered), \
             patch.object(session_queries_module, "_build_cycles", return_value=[SimpleNamespace(cycle_number=1)]):
            cycles = query.resolve_sessions(info, by_cycles=True)
        self.assertTrue(cycles.by_cycles)
        resources = MagicMock()
        resources.filter.return_value = resources
        resources.count.return_value = 4
        resources.__getitem__.return_value = [SimpleNamespace(id=1)]
        with patch.object(session_queries_module.DigitalResource.objects, "all", return_value=resources):
            result = query.resolve_digital_resources(info, type="audio", search="x", page_size=2)
        self.assertEqual(result.total_pages, 2)

    def test_finance_mutations_update_and_delete_paths(self):
        expense = SimpleNamespace(status="pending", save=MagicMock())
        with patch.object(finance_mutations_module.Expense.objects, "get", return_value=expense):
            result = finance_mutations_module.UpdateExpenseStatus.mutate(None, None, "1", "paid")
        self.assertEqual(result.expense, expense)
        self.assertEqual(expense.status, "paid")
        with patch.object(finance_mutations_module.Expense.objects, "get", side_effect=finance_mutations_module.Expense.DoesNotExist):
            with self.assertRaisesRegex(Exception, "Gasto no encontrado"):
                finance_mutations_module.UpdateExpenseStatus.mutate(None, None, "1", "paid")

        deleted = SimpleNamespace(delete=MagicMock())
        with patch.object(finance_mutations_module.Expense.objects, "get", return_value=deleted):
            self.assertTrue(finance_mutations_module.DeleteExpense.mutate(None, None, "1").success)
        course = SimpleNamespace(save=MagicMock())
        with patch.object(finance_mutations_module.Course.objects, "get", return_value=course):
            result = finance_mutations_module.UpdateCourse.mutate(None, None, "1", price=12.5, name="Course")
        self.assertEqual(str(course.price), "12.5")
        self.assertEqual(result.course, course)
        discount = SimpleNamespace(save=MagicMock(), delete=MagicMock())
        with patch.object(finance_mutations_module.Discount.objects, "get", return_value=discount):
            result = finance_mutations_module.UpdateDiscount.mutate(None, None, "1", value=5, description="x")
        self.assertEqual(str(discount.value), "5")
        self.assertEqual(result.discount, discount)

        course = SimpleNamespace(delete=MagicMock())
        with patch.object(finance_mutations_module.Course.objects, "get", return_value=course):
            self.assertTrue(finance_mutations_module.DeleteCourse.mutate(None, None, "1").success)
        with patch.object(finance_mutations_module.Discount.objects, "get", return_value=discount):
            self.assertTrue(finance_mutations_module.DeleteDiscount.mutate(None, None, "1").success)
        with patch.object(finance_mutations_module.Discount.objects, "get", side_effect=finance_mutations_module.Discount.DoesNotExist):
            self.assertFalse(finance_mutations_module.DeleteDiscount.mutate(None, None, "1").success)

    def test_institution_mutations_cover_crud_and_not_found_paths(self):
        institution = SimpleNamespace(contact_phone="", save=MagicMock(), delete=MagicMock())
        with patch.object(institutions_mutations_module.Institution.objects, "filter", return_value=MagicMock(exists=MagicMock(return_value=False))), \
             patch.object(institutions_mutations_module.Institution.objects, "create", return_value=institution):
            self.assertIs(institutions_mutations_module.CreateInstitution.mutate(None, None, "Clinic").institution, institution)
        with patch.object(institutions_mutations_module.Institution.objects, "get", return_value=institution):
            result = institutions_mutations_module.UpdateInstitution.mutate(None, None, "1", name="New", phone="123")
        self.assertEqual(institution.contact_phone, "123")
        self.assertIs(result.institution, institution)
        with patch.object(institutions_mutations_module.Institution.objects, "get", return_value=institution):
            self.assertTrue(institutions_mutations_module.DeleteInstitution.mutate(None, None, "1").success)
        group = SimpleNamespace(name="Old", save=MagicMock(), delete=MagicMock())
        with patch.object(institutions_mutations_module.Institution.objects, "get", return_value=institution), \
             patch.object(institutions_mutations_module.InstitutionGroup.objects, "create", return_value=group):
            self.assertIs(institutions_mutations_module.CreateInstitutionGroup.mutate(None, None, "1", "G").group, group)
        with patch.object(institutions_mutations_module.InstitutionGroup.objects, "get", return_value=group):
            self.assertIs(institutions_mutations_module.UpdateInstitutionGroup.mutate(None, None, "1", "New").group, group)
            self.assertTrue(institutions_mutations_module.DeleteInstitutionGroup.mutate(None, None, "1").success)

    def test_clinical_mutation_update_and_delete_paths(self):
        info = SimpleNamespace(context=SimpleNamespace(user=SimpleNamespace(
            is_authenticated=True, is_staff=True, is_superuser=False, pk=1,
        )))
        patient = SimpleNamespace(pk=1, save=MagicMock(), status="active")
        with patch.object(clinical_mutations_module, "user_can_access_patient", return_value=True), \
             patch.object(clinical_mutations_module.Patient.objects, "get", return_value=patient):
            result = clinical_mutations_module.UpdatePatient.mutate(None, info, "1", diagnosis="updated", registration_complete=True)
            self.assertIs(result.patient, patient)
            self.assertTrue(clinical_mutations_module.DeletePatient.mutate(None, info, "1").success)
        plan = SimpleNamespace(patient_id=1, progress_percent=0, save=MagicMock(), delete=MagicMock())
        with patch.object(clinical_mutations_module, "user_can_access_patient", return_value=True), \
             patch.object(clinical_mutations_module.InterventionPlan.objects, "get", return_value=plan):
            self.assertIs(clinical_mutations_module.UpdatePlanProgress.mutate(None, info, "1", 120).plan, plan)
            self.assertTrue(clinical_mutations_module.DeleteInterventionPlan.mutate(None, info, "1").success)
        step = SimpleNamespace(plan=SimpleNamespace(patient_id=1), save=MagicMock(), delete=MagicMock())
        with patch.object(clinical_mutations_module, "user_can_access_patient", return_value=True), \
             patch.object(clinical_mutations_module.PlanStep.objects, "get", return_value=step):
            self.assertIs(clinical_mutations_module.UpdateStepPlan.mutate(None, info, "1", objective="x").step, step)
            self.assertTrue(clinical_mutations_module.DeleteStepPlan.mutate(None, info, "1").success)

    def test_evaluation_form_mutations_cover_create_delete_and_assign(self):
        info = SimpleNamespace(context=SimpleNamespace(user=SimpleNamespace(
            is_authenticated=True, is_staff=True, is_superuser=False, pk=1,
        )))
        form = SimpleNamespace(delete=MagicMock())
        questions = [SimpleNamespace(question="Q1", question_type="text", is_required=None, order_index=None)]
        with patch.object(evaluations_mutations_module.Form.objects, "create", return_value=form), \
             patch.object(evaluations_mutations_module.FormQuestion.objects, "create") as create_question:
            result = evaluations_mutations_module.CreateForm.mutate(None, info, "Form", questions, "Description")
        self.assertIs(result.form, form)
        create_question.assert_called_once()
        with patch.object(evaluations_mutations_module.Form.objects, "get", return_value=form):
            self.assertTrue(evaluations_mutations_module.DeleteForm.mutate(None, info, "1").success)
        assignment = SimpleNamespace()
        with patch.object(evaluations_mutations_module.FormAssignment.objects, "create", return_value=assignment):
            result = evaluations_mutations_module.AssignForm.mutate(None, info, "1", "1", assigned_to_id="2", patient_id="3", session_id="4")
        self.assertIs(result.assignment, assignment)

    def test_pipeline_sample_annotation_update_and_artifact_endpoints(self):
        user = SimpleNamespace(is_authenticated=True, is_staff=True)
        features = {name: 1.0 for name in pipeline_models_module.DATASET_FEATURE_COLUMNS}
        labels = {"visual__MOVIMIENTO": 1}
        sample = SimpleNamespace(
            id=1, pk=1, session_id="S1", window_id="W1", features=features, labels=labels,
            reviewed=False, start_time=0, end_time=1, demuca_phase="MOVIMIENTO",
            sound_tags=[], movement_tags=[], interaction_tags=[], derived_features={},
            pose_landmarks=[], artifact_payload={}, updated_at=SimpleNamespace(isoformat=lambda: "now"),
            save=MagicMock(),
        )
        samples = MagicMock()
        samples.filter.return_value.first.return_value = sample
        dataset = SimpleNamespace(id=1, samples=samples)
        body = json.dumps({"session_id": "S1", "window_id": "W1", "features": features, "labels": labels}).encode()
        request = SimpleNamespace(user=user, method="POST", headers={}, body=body)
        with patch.object(pipeline_views_module, "_dataset_for_user", return_value=dataset), \
             patch.object(pipeline_views_module.TherapistDatasetSample.objects, "filter", return_value=MagicMock(exists=MagicMock(return_value=False))), \
             patch.object(pipeline_views_module.TherapistDatasetSample.objects, "create", return_value=sample):
            response = pipeline_views_module.create_dataset_sample(request, 1)
        self.assertEqual(response.status_code, 201)

        annotation_body = {
            "session_id": "S1", "window_id": "A1", "start_time": 0, "end_time": 1,
            "demuca_phase": "MOVIMIENTO", "sound_tags": [], "movement_tags": [],
            "interaction_tags": [], "derived_features": {}, "pose_landmarks": [],
            "artifact_payload": {}, "features": features, "labels": labels,
        }
        request.body = json.dumps(annotation_body).encode()
        with patch.object(pipeline_views_module, "_dataset_for_user", return_value=dataset), \
             patch.object(pipeline_views_module.TherapistDatasetSample.objects, "filter", return_value=MagicMock(exists=MagicMock(return_value=False))), \
             patch.object(pipeline_views_module.TherapistDatasetSample.objects, "create", return_value=sample):
            response = pipeline_views_module.create_dataset_annotation(request, 1)
        self.assertEqual(response.status_code, 201)

        request.method = "PATCH"
        request.body = json.dumps({"features": features, "labels": labels, "reviewed": True}).encode()
        with patch.object(pipeline_views_module, "_dataset_for_user", return_value=dataset):
            response = pipeline_views_module.update_dataset_sample(request, 1, 1)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(sample.reviewed)

        request.method = "GET"
        with patch.object(pipeline_views_module, "_artifact_payload_for_session", return_value=({"x": 1}, [])):
            response = pipeline_views_module.session_artifacts_for_user(request, "S1")
        self.assertEqual(response.status_code, 200)
        result = SimpleNamespace(resultado={"pose_landmarks": [1]})
        with patch.object(pipeline_views_module, "_dataset_for_user", return_value=dataset), \
             patch.object(pipeline_views_module.ResultadoAnalisis.objects, "filter", return_value=MagicMock(first=MagicMock(return_value=result))):
            response = pipeline_views_module.session_artifacts(request, 1, "S1")
        self.assertEqual(response.status_code, 200)

    def test_pipeline_annotation_authorization_and_lineage_views(self):
        user = SimpleNamespace(is_authenticated=True, is_staff=True)
        sample = SimpleNamespace(
            pk=2, session_id="S2", start_time=0, end_time=1, demuca_phase="MOVIMIENTO",
            sound_tags=[], movement_tags=[], interaction_tags=[], pose_landmarks=[],
            derived_features={}, updated_at=SimpleNamespace(isoformat=lambda: "now"),
        )
        sample_qs = MagicMock()
        sample_qs.filter.return_value = sample_qs
        sample_qs.order_by.return_value = [sample]
        sample_qs.count.return_value = 0
        sample_qs.exists.side_effect = [True, False]
        dataset = SimpleNamespace(
            id=1, name="D", description="", status="draft", training_authorized=False,
            authorized_at=None, created_at=SimpleNamespace(isoformat=lambda: "c"),
            updated_at=SimpleNamespace(isoformat=lambda: "u"), samples=sample_qs,
        )
        sample_qs.count.return_value = 1
        sample_qs.filter.return_value.count.return_value = 0
        sample_qs.all.return_value = sample_qs
        request = SimpleNamespace(user=user, method="GET", headers={}, body=b"")
        with patch.object(pipeline_views_module, "_annotation_dataset_for_user", return_value=dataset):
            response = pipeline_views_module.annotation_windows(request, "S2")
        self.assertEqual(response.status_code, 200)

        dataset.training_authorized = False
        dataset.status = "draft"
        dataset.save = MagicMock()
        dataset.authorized_at = None
        with patch.object(pipeline_views_module.TherapistDataset.objects, "filter", return_value=MagicMock(first=MagicMock(return_value=dataset))):
            response = pipeline_views_module.authorize_dataset(SimpleNamespace(user=user, method="POST", headers={}, body=b""), 1)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(dataset.training_authorized)

        result = SimpleNamespace(
            session_id="S2", estado="completed", mlflow_run_id="r", mlflow_experiment="e",
            mlflow_model_name="m", mlflow_model_version="1", model_sha256="h",
            dataset_hash="d", creado_en=SimpleNamespace(isoformat=lambda: "now"),
        )
        with patch.object(pipeline_views_module.ResultadoAnalisis.objects, "filter", return_value=MagicMock(first=MagicMock(return_value=result))):
            response = pipeline_views_module.obtener_lineage_mlops(request, "S2")
        self.assertEqual(response.status_code, 200)
        listed = MagicMock()
        listed.__iter__.return_value = iter([result])
        with patch.object(pipeline_views_module.ResultadoAnalisis.objects, "exclude", return_value=MagicMock(order_by=MagicMock(return_value=listed))):
            response = pipeline_views_module.listar_modelos_mlops(request)
        self.assertEqual(response.status_code, 200)

    def test_window_index_builds_full_windows_and_validates_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "S1"
            segments_dir = session / "processed" / "segments"
            features_dir = session / "processed" / "features"
            segments_dir.mkdir(parents=True)
            features_dir.mkdir(parents=True)
            for relative in ("window_000000/video.mp4", "window_000000/audio.wav", "window_000001/video.mp4", "window_000001/audio.wav"):
                path = segments_dir / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"segment")
            segments = {
                "session_id": "S1", "window_seconds": 1, "effective_duration_seconds": 1.5,
                "clock": "seconds", "drift_tolerance_seconds": 0.1,
                "segments": [
                    {"index": 0, "start_seconds": 0, "end_seconds": 1, "duration_seconds": 1,
                     "video": "window_000000/video.mp4", "audio": "window_000000/audio.wav", "sync_drift_seconds": 0},
                    {"index": 1, "start_seconds": 1, "end_seconds": 1.5, "duration_seconds": 0.5,
                     "video": "window_000001/video.mp4", "audio": "window_000001/audio.wav", "sync_drift_seconds": 0},
                ],
            }
            (segments_dir / "segments.json").write_text(json.dumps(segments))
            for name in ("audio_features.json", "visual_motion.json"):
                (features_dir / name).write_text(json.dumps({"timestamps": [0, 0.5, 1, 1.5], "value": [1, 2, 3, 4]}))
            index = build_window_index(session)
            self.assertEqual(index["complete_windows"], 1)
            self.assertEqual(len(index["excluded_segments"]), 1)
            self.assertEqual(validate_window_index(index, session), [])
            broken = dict(index)
            broken["schema_version"] = "0"
            self.assertIn("unsupported_schema_version", validate_window_index(broken, session))

    def test_media_manifest_normalization_executes_and_reuses_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "S1"
            session.mkdir()
            manifest = session / "session_manifest.json"
            source = session / "raw.mp4"
            source.write_bytes(b"raw")
            manifest.write_text(json.dumps({
                "session_id": "S1", "source_version": "1", "duration_seconds": 1,
                "timeline_policy": "contiguous", "fragments": [{
                    "fragment_id": "f1", "global_start_seconds": 0,
                    "duration_seconds": 1, "video_path": "raw.mp4", "audio_path": None,
                }],
            }))
            with patch.object(media, "load_and_validate_session_manifest", return_value={"valid": True}), \
                 patch.object(media, "_process_manifest_fragment", return_value=([], [], 1.0)), \
                 patch.object(media, "probe_stream_duration", return_value=1.0):
                def concat(staging, video_parts, audio_parts):
                    video, audio = staging / "normalized.mp4", staging / "normalized.wav"
                    video.write_bytes(b"v")
                    audio.write_bytes(b"a")
                    return video, audio
                with patch.object(media, "_concat_manifest_parts", side_effect=concat):
                    result = media.normalize_manifest_fragments(session, manifest)
            self.assertEqual(result["status"], "executed")
            self.assertTrue((session / "processed" / "manifest_processing.json").is_file())
            with patch.object(media, "load_and_validate_session_manifest", return_value={"valid": True}):
                reused = media.normalize_manifest_fragments(session, manifest)
            self.assertEqual(reused["status"], "reused")

    def test_laravel_import_command_remote_and_row_helpers(self):
        command = laravel_command_module.Command()
        cursor = MagicMock()
        cursor.fetchall.return_value = [{"id": 1, "nombre": "Ana"}]
        connection = MagicMock()
        connection.cursor.return_value = cursor
        rows = command._query_remote_db(connection, "usuarios")
        self.assertEqual(rows[0][0], "1")
        cursor.close.assert_called_once()
        with patch.object(laravel_command_module.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="1\tAna\n", stderr="")):
            rows = command._query_remote_db({"ssh": True, "user": "u", "password": "p", "database": "d", "host": "h"}, "usuarios")
        self.assertEqual(rows, [["1", "Ana"]])
        with self.assertRaises(Exception):
            command._remote_columns("not_allowed")

        fake_user = SimpleNamespace(set_password=MagicMock(), save=MagicMock())
        with patch.object(laravel_command_module.User.objects, "update_or_create", return_value=(fake_user, True)):
            users = command._import_users([["1", "Ana", "Lopez", "", "", "700", "", "123", "", "activo", "", "", "", "visible", "", ""]])
        self.assertIn("ana lopez", users)
        payment = SimpleNamespace()
        info = {"patient": SimpleNamespace()}
        with patch.object(laravel_command_module.Payment.objects, "create", return_value=payment):
            imported = command._import_payments(
                [["10", "20", "100", "", "50", "", "", "", "", "", ""]],
                {20: info}, {10: "proof.pdf"}, {10: 2},
            )
        self.assertIs(imported[10], payment)

    def test_laravel_import_command_patients_sessions_and_lookup_helpers(self):
        command = laravel_command_module.Command()
        patient = SimpleNamespace(
            diagnosis="", residence="", notes="", save=MagicMock(), tutor=None,
        )
        with patch.object(laravel_command_module.Patient.objects, "update_or_create", return_value=(patient, True)):
            patients = {}
            command._import_client_row(["1", "Ana", "Lopez", "", "", "", "", "2000-01-02", "0", "", "activo", "", ""], patients)
        self.assertIs(patients[1], patient)
        tutor = SimpleNamespace(set_password=MagicMock(), save=MagicMock())
        with patch.object(command, "_resolve_or_create_tutor_user", return_value=tutor), \
             patch.object(command, "_upsert_clinical_note") as note:
            info_map = {}
            command._import_info_row(
                ["10", "1", "diag", "res", "", "", "", "Tutor", "", "obj", "fis", "emo", "cog", "soc", "met", "notes", "extra", "", ""],
                patients, info_map, {}, SimpleNamespace(id=2),
            )
        self.assertIs(info_map[10]["patient"], patient)
        self.assertGreaterEqual(note.call_count, 1)
        self.assertEqual(command._extract_payment_proofs([["", "10", "", "", "", "proof", "", "", "", ""]]), {10: "proof"})
        self.assertEqual(command._count_cycles_by_payment([["", "10"] + [""] * 11])[10], 1)


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

    def test_media_extraction_and_segmentation_helpers_cover_reuse_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = root / "dataset" / "dataset" / "sessions" / "S1"
            metadata = session / "metadata"
            video_dir = session / "processed" / "video"
            audio_dir = session / "processed" / "audio"
            features = session / "processed" / "features"
            frames = session / "processed" / "frames"
            for directory in (metadata, video_dir, audio_dir, features, frames):
                directory.mkdir(parents=True)
            (metadata / "session.json").write_text("{}")
            (video_dir / "S1_1280x720_10fps.mp4").write_bytes(b"v")
            (audio_dir / "S1_16khz_mono.wav").write_bytes(b"a")
            (features / "audio_features.json").write_text("{}")
            (features / "visual_motion.json").write_text("{}")
            (frames / "S1_0000.jpg").write_bytes(b"f")
            with patch.object(media, "_run_extraction_stages", return_value=({"stage": "reused"}, False)):
                self.assertEqual(media.run_existing_extraction("S1", root), {"stage": "reused"})

            invoke = patcher = patch.object(media, "run_command", return_value="")
            with invoke as run:
                gap_video, gap_audio = media._create_gap_parts(root, 0, 0.5)
                self.assertTrue(gap_video.name.endswith("gap.mp4"))
                self.assertTrue(gap_audio.name.endswith("gap.wav"))
                self.assertEqual(run.call_count, 2)

            staging = root / "staging"
            staging.mkdir()
            source_video = root / "source.mp4"
            source_audio = root / "source.wav"
            source_video.write_bytes(b"v")
            source_audio.write_bytes(b"a")
            with patch.object(media, "run_command") as run:
                video_part = media._create_video_part(staging, 1, source_video, 1.0)
                audio_part = media._create_audio_part(staging, 1, source_audio, 1.0, False, 0.1)
                self.assertEqual(video_part.name, "part-000001-video.mp4")
                self.assertEqual(audio_part.name, "part-000001-audio.wav")
                self.assertEqual(run.call_count, 2)

            with patch.object(media, "_segment_window", return_value=({"index": 0}, 0.02)):
                records, drift = media._build_segments(staging, source_video, source_audio, 1, 1.5, 0.1)
            self.assertEqual(len(records), 2)
            self.assertEqual(drift, 0.02)

            with patch.object(media, "probe_stream_duration", side_effect=[1.0, 1.1]):
                info = media._segment_source_info(source_video, source_audio, 0.2)
            self.assertEqual(info[3], "audio")
            self.assertEqual(info[-1], 1.0)

    def test_media_manifest_and_segment_helpers_reject_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"session_id": "S2"}))
            with self.assertRaisesRegex(ValueError, "manifest session_id"):
                media._normalize_extraction(
                    "S1", root, root / "manifest.json", True, root / "v", root / "a", False,
                    lambda _: None,
                )
            manifest.write_text(json.dumps({"session_id": "S1"}))
            with self.assertRaisesRegex(ValueError, "manifest session_id"):
                media._normalize_extraction(
                    "S2", root, manifest, True, root / "v", root / "a", False,
                    lambda _: None,
                )
            with patch.object(media, "run_command"), patch.object(media, "probe_stream_duration", side_effect=[1.0, 1.5]):
                with self.assertRaisesRegex(ValueError, "window drift"):
                    media._segment_window(root, root / "v", root / "a", 0, 0, 1, 0.1)

    def test_media_normalizes_valid_manifest_without_running_ffmpeg(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "S1"
            session.mkdir()
            manifest = session / "session_manifest.json"
            source_video = session / "raw.mp4"
            source_audio = session / "raw.wav"
            source_video.write_bytes(b"video")
            source_audio.write_bytes(b"audio")
            manifest.write_text(json.dumps({
                "session_id": "S1", "source_version": "v1", "duration_seconds": 1,
                "timeline_policy": "contiguous",
                "fragments": [{
                    "fragment_id": "F1", "global_start_seconds": 0,
                    "duration_seconds": 1, "video_path": "raw.mp4", "audio_path": "raw.wav",
                }],
            }))

            def concat(staging, video_parts, audio_parts):
                video = staging / "normalized.mp4"
                audio = staging / "normalized.wav"
                video.write_bytes(b"normalized video")
                audio.write_bytes(b"normalized audio")
                return video, audio

            with patch.object(media, "load_and_validate_session_manifest", return_value={"valid": True}), \
                 patch.object(media, "_process_manifest_fragment", return_value=([], [], 1.0)), \
                 patch.object(media, "_concat_manifest_parts", side_effect=concat), \
                 patch.object(media, "probe_stream_duration", side_effect=[1.0, 1.0]):
                result = media.normalize_manifest_fragments(session, manifest)
            self.assertEqual(result["status"], "executed")
            self.assertTrue((session / "processed" / "video" / "S1_1280x720_10fps.mp4").is_file())
            self.assertTrue((session / "processed" / "manifest_processing.json").is_file())

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
