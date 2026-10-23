import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="multimodal-test-"))
class AnalisisVideoHttpTests(SimpleTestCase):
    def test_rechaza_peticion_sin_video(self):
        respuesta = self.client.post("/api/multimodal/analizar-video/")

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.json()["status"], "failed")

    def test_adapta_video_a_respuesta_json(self):
        cuerpo = {"status": "completed", "session_id": "HTTP-001", "demuca": {"status": "not_available"}}
        archivo = SimpleUploadedFile("sesion.mp4", b"video", content_type="video/mp4")
        with (
            patch("multimodal.views._python_ml", return_value=Path("/usr/bin/python")),
            patch("multimodal.views.subprocess.run") as ejecutar,
        ):
            ejecutar.return_value.returncode = 0
            ejecutar.return_value.stdout = json.dumps(cuerpo)
            ejecutar.return_value.stderr = ""
            respuesta = self.client.post(
                "/api/multimodal/analizar-video/",
                {"video": archivo, "session_id": "HTTP-001"},
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), cuerpo)
        comando = ejecutar.call_args.args[0]
        self.assertIn("ml/analyze_video.py", " ".join(comando))
        self.assertIn("HTTP-001", comando)
