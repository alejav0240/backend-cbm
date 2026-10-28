import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.conf import settings
from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase, override_settings

from pipeline_multimodal.models import ResultadoAnalisis, TrabajoAnalisis
from pipeline_multimodal.servicios import ErrorPipelineMultimodal
from pipeline_multimodal.demuca_review import merge_demuca_data


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="pipeline-multimodal-test-"), DEBUG=True)
class PipelineMultimodalTests(SimpleTestCase):
    def test_merge_demuca_data_normaliza_edicion_parcial(self):
        result = merge_demuca_data(
            {"sesion_id": "PIPE-001", "movimiento_corporal": {"andar": 1}},
            {"movimiento_corporal": {"andar": 2}},
            session_id="PIPE-001",
        )
        self.assertEqual(result["movimiento_corporal"]["andar"], 2)
        self.assertEqual(result["movimiento_corporal"]["correr"], 0)

    def test_merge_demuca_data_rechaza_valor_negativo(self):
        with self.assertRaisesMessage(ValueError, "demuca_value_must_be_non_negative"):
            merge_demuca_data(
                None,
                {"movimiento_corporal": {"andar": -1}},
                session_id="PIPE-001",
            )

    def test_publica_resultado_del_servicio(self):
        archivo = SimpleUploadedFile("sesion.mp4", b"video", content_type="video/mp4")
        cuerpo = {"status": "completed", "session_id": "PIPE-001"}
        with (
            patch("pipeline_multimodal.views.ServicioPipelineMultimodal.ejecutar", return_value=cuerpo) as ejecutar,
            patch("pipeline_multimodal.views.ResultadoAnalisis.objects.create"),
        ):
            respuesta = self.client.post(
                "/api/pipeline-multimodal/analizar-video/",
                {"video": archivo, "session_id": "PIPE-001"},
                HTTP_X_SERVICE_KEY="",
            )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), cuerpo)
        self.assertEqual(ejecutar.call_args.args[1], "PIPE-001")
        self.assertIn("X-Request-ID", respuesta)

    def test_servicio_construye_comando_cli(self):
        servicio = __import__("pipeline_multimodal.servicios", fromlist=["ServicioPipelineMultimodal"]).ServicioPipelineMultimodal(
            Path("/proyecto"), Path("/usr/bin/python"), timeout=3
        )
        with patch("pipeline_multimodal.servicios.subprocess.run") as ejecutar:
            ejecutar.return_value.returncode = 0
            ejecutar.return_value.stdout = json.dumps({"status": "completed"})
            ejecutar.return_value.stderr = ""
            resultado = servicio.ejecutar(Path("/tmp/video.mp4"), "PIPE-001")
        self.assertEqual(resultado["status"], "completed")
        self.assertIn("ml/analyze_video.py", " ".join(ejecutar.call_args.args[0]))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="pipeline-multimodal-async-test-"), DEBUG=True)
class PipelineMultimodalAsyncTests(TestCase):
    def test_terapeuta_puede_persistir_edicion_demuca_sin_autorizar_entrenamiento(self):
        ResultadoAnalisis.objects.create(
            session_id="SESSION-HITL",
            resultado={
                "status": "completed",
                "session_id": "SESSION-HITL",
                "demuca": {"status": "draft", "data": {"sesion_id": "SESSION-HITL"}},
            },
        )

        respuesta = self.client.patch(
            "/api/pipeline-multimodal/resultados/SESSION-HITL/demuca/",
            data=json.dumps({"demuca": {"movimiento_corporal": {"andar": 2}}}),
            content_type="application/json",
            HTTP_X_SERVICE_KEY="",
        )

        self.assertEqual(respuesta.status_code, 200)
        payload = respuesta.json()
        self.assertEqual(payload["demuca"]["status"], "human_reviewed")
        self.assertEqual(payload["demuca"]["data"]["movimiento_corporal"]["andar"], 2)
        self.assertFalse(payload["demuca"]["training_authorized"])

    def test_reutiliza_trabajo_activo_para_evitar_duplicados(self):
        existente = TrabajoAnalisis.objects.create(
            session_id="SESSION-001", archivo_path="/tmp/existing.mp4"
        )
        archivo = SimpleUploadedFile("sesion.mp4", b"video", content_type="video/mp4")

        respuesta = self.client.post(
            "/api/pipeline-multimodal/trabajos/",
            {"video": archivo, "session_id": "SESSION-001"},
            HTTP_X_SERVICE_KEY="",
            HTTP_X_REQUEST_ID="upload-job-001",
        )

        self.assertEqual(respuesta.status_code, 202)
        self.assertEqual(respuesta.json()["job_id"], str(existente.job_id))
        self.assertTrue(respuesta.json()["duplicado"])
        self.assertEqual(TrabajoAnalisis.objects.filter(session_id="SESSION-001").count(), 1)

    @patch("pipeline_multimodal.management.commands.procesar_pipeline_multimodal.ServicioPipelineMultimodal.configurado")
    def test_worker_preserva_archivo_si_el_pipeline_falla(self, configurado):
        archivo = Path(settings.MEDIA_ROOT) / "pipeline_jobs" / "job.mp4"
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_bytes(b"video")
        trabajo = TrabajoAnalisis.objects.create(
            session_id="SESSION-002", request_id="request-002", archivo_path=str(archivo)
        )
        configurado.return_value.ejecutar.side_effect = ErrorPipelineMultimodal("fallo ML")

        call_command("procesar_pipeline_multimodal", "--once")

        trabajo.refresh_from_db()
        self.assertEqual(trabajo.estado, TrabajoAnalisis.Estado.FALLIDO)
        self.assertEqual(trabajo.error, "fallo ML")
        self.assertTrue(archivo.exists())

    @patch("pipeline_multimodal.management.commands.procesar_pipeline_multimodal.ServicioPipelineMultimodal.configurado")
    def test_worker_elimina_archivo_solo_despues_de_completar(self, configurado):
        archivo = Path(settings.MEDIA_ROOT) / "pipeline_jobs" / "job.mp4"
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_bytes(b"video")
        trabajo = TrabajoAnalisis.objects.create(
            session_id="SESSION-003", request_id="request-003", archivo_path=str(archivo)
        )
        configurado.return_value.ejecutar.return_value = {
            "status": "completed", "session_id": "SESSION-003"
        }

        call_command("procesar_pipeline_multimodal", "--once")

        trabajo.refresh_from_db()
        self.assertEqual(trabajo.estado, TrabajoAnalisis.Estado.COMPLETADO)
        self.assertEqual(trabajo.resultado["status"], "completed")
        resultado = ResultadoAnalisis.objects.get(session_id="SESSION-003")
        self.assertEqual(resultado.resultado["status"], "completed")
        self.assertFalse(archivo.exists())

    def test_reintento_fallido_no_sobrescribe_archivo_original_si_falla_db(self):
        archivo = Path(settings.MEDIA_ROOT) / "pipeline_jobs" / "old.mp4"
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_bytes(b"original")
        TrabajoAnalisis.objects.create(
            session_id="SESSION-004", request_id="request-004", archivo_path=str(archivo),
            estado=TrabajoAnalisis.Estado.FALLIDO, error="fallo anterior",
        )
        nuevo = SimpleUploadedFile("nuevo.mp4", b"nuevo", content_type="video/mp4")

        with patch.object(TrabajoAnalisis, "save", side_effect=RuntimeError("db down")):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    "/api/pipeline-multimodal/trabajos/",
                    {"video": nuevo, "session_id": "SESSION-004"},
                    HTTP_X_SERVICE_KEY="",
                    HTTP_X_REQUEST_ID="request-004-retry",
                )

        self.assertEqual(archivo.read_bytes(), b"original")

    @patch("pipeline_multimodal.management.commands.procesar_pipeline_multimodal.ServicioPipelineMultimodal.configurado")
    def test_worker_actualiza_el_resultado_mas_reciente_sin_romper_historial(self, configurado):
        archivo = Path(settings.MEDIA_ROOT) / "pipeline_jobs" / "history.mp4"
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_bytes(b"video")
        TrabajoAnalisis.objects.create(
            session_id="SESSION-005", request_id="request-005", archivo_path=str(archivo)
        )
        ResultadoAnalisis.objects.create(
            session_id="SESSION-005", request_id="old-005", resultado={"status": "completed"}
        )
        ResultadoAnalisis.objects.create(
            session_id="SESSION-005", request_id="new-005", resultado={"status": "completed"}
        )
        configurado.return_value.ejecutar.return_value = {
            "status": "completed", "session_id": "SESSION-005"
        }

        call_command("procesar_pipeline_multimodal", "--once")

        self.assertEqual(ResultadoAnalisis.objects.filter(session_id="SESSION-005").count(), 2)
        self.assertEqual(
            ResultadoAnalisis.objects.filter(session_id="SESSION-005").order_by("-creado_en", "-pk").first().request_id,
            "request-005",
        )

    @patch("pipeline_multimodal.management.commands.procesar_pipeline_multimodal.ServicioPipelineMultimodal.configurado")
    @patch("pipeline_multimodal.management.commands.procesar_pipeline_multimodal.ResultadoAnalisis.objects.create")
    def test_worker_marca_fallo_si_no_puede_publicar_resultado(self, crear_resultado, configurado):
        archivo = Path(settings.MEDIA_ROOT) / "pipeline_jobs" / "publish-failure.mp4"
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_bytes(b"video")
        trabajo = TrabajoAnalisis.objects.create(
            session_id="SESSION-006", request_id="request-006", archivo_path=str(archivo)
        )
        configurado.return_value.ejecutar.return_value = {
            "status": "completed", "session_id": "SESSION-006"
        }
        crear_resultado.side_effect = RuntimeError("database unavailable")

        call_command("procesar_pipeline_multimodal", "--once")

        trabajo.refresh_from_db()
        self.assertEqual(trabajo.estado, TrabajoAnalisis.Estado.FALLIDO)
        self.assertIn("No se pudo persistir el resultado", trabajo.error)
        self.assertTrue(archivo.exists())

    def test_bd_impide_dos_trabajos_activos_para_la_misma_sesion(self):
        TrabajoAnalisis.objects.create(
            session_id="SESSION-007", request_id="request-007", archivo_path="/tmp/one.mp4"
        )

        with self.assertRaises(IntegrityError):
            TrabajoAnalisis.objects.create(
                session_id="SESSION-007", request_id="request-008", archivo_path="/tmp/two.mp4"
            )
