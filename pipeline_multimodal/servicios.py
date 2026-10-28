"""Casos de uso del módulo de pipeline multimodal."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


class ErrorPipelineMultimodal(Exception):
    """Error controlado al ejecutar el proceso ML externo."""


class ServicioPipelineMultimodal:
    """Ejecuta el CLI ML sin acoplar la vista a subprocess ni a rutas locales."""

    def __init__(self, raiz: Path, interprete: Path, timeout: int = 1800):
        self.raiz = raiz
        self.interprete = interprete
        self.timeout = timeout

    @classmethod
    def configurado(cls) -> "ServicioPipelineMultimodal":
        raiz = Path(os.environ.get("MULTIMODAL_PROJECT_ROOT", Path(__file__).resolve().parents[1])).resolve()
        interprete = Path(os.environ.get("MULTIMODAL_PYTHON", sys.executable)).resolve()
        timeout = int(os.environ.get("MULTIMODAL_TIMEOUT_SECONDS", "1800"))
        return cls(raiz, interprete, timeout)

    def ejecutar(self, entrada: Path, session_id: str) -> dict:
        if not self.interprete.is_file():
            raise ErrorPipelineMultimodal("Entorno ML no disponible.")
        comando = [
            str(self.interprete), str(self.raiz / "ml" / "analyze_video.py"), str(entrada),
            "--session-id", session_id, "--project-root", str(self.raiz),
        ]
        if os.environ.get("MULTIMODAL_DEMO_MODE", "false").lower() == "true":
            demo_model = Path(
                os.environ.get(
                    "MULTIMODAL_DEMO_MODEL",
                    str(self.raiz / "ml" / "artifacts" / "demo_mvp" / "models" / "gradient_boosting_late_fusion.joblib"),
                )
            )
            comando.extend([
                "--prediction-model", str(demo_model),
                "--allow-experimental-demo",
            ])
        try:
            resultado = subprocess.run(
                comando, cwd=self.raiz, check=False, capture_output=True,
                text=True, timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as error:
            raise ErrorPipelineMultimodal("El análisis excedió el tiempo límite.") from error
        try:
            cuerpo = json.loads(resultado.stdout or "{}")
        except json.JSONDecodeError as error:
            raise ErrorPipelineMultimodal(
                resultado.stderr.strip() or "El analizador no devolvió JSON válido."
            ) from error
        if not isinstance(cuerpo, dict) or cuerpo.get("status") not in {"completed", "failed", "blocked"}:
            raise ErrorPipelineMultimodal("El analizador devolvió un contrato inválido.")
        if resultado.returncode != 0:
            raise ErrorPipelineMultimodal(str(cuerpo.get("error") or resultado.stderr.strip() or "Falló el análisis multimodal."))
        return cuerpo
