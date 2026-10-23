import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="pipeline-multimodal-test-"), DEBUG=True)
class PipelineMultimodalTests(SimpleTestCase):
    def test_publica_resultado_del_servicio(self):
        archivo = SimpleUploadedFile("sesion.mp4", b"video", content_type="video/mp4")
        cuerpo = {"status": "completed", "session_id": "PIPE-001"}
        with patch("pipeline_multimodal.views.ServicioPipelineMultimodal.ejecutar", return_value=cuerpo) as ejecutar:
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
