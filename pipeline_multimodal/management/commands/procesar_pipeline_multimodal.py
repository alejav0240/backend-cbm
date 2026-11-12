from django.core.management.base import BaseCommand
from django.db import transaction
from pathlib import Path
import time

from django.conf import settings
from pipeline_multimodal.models import ResultadoAnalisis, TrabajoAnalisis
from pipeline_multimodal.views import _mlops_lineage
from pipeline_multimodal.servicios import ErrorPipelineMultimodal, ServicioPipelineMultimodal


def _managed_job_path(value):
    if not isinstance(value, str) or not value:
        return None
    root = Path(settings.MEDIA_ROOT).resolve()
    candidate = Path(value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


class Command(BaseCommand):
    help = "Procesa trabajos encolados del pipeline multimodal."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Procesa un trabajo y termina.")
        parser.add_argument(
            "--poll-seconds",
            type=float,
            default=0,
            help="Mantiene el worker activo y consulta la cola con este intervalo.",
        )

    def handle(self, *args, **options):
        procesados = 0
        intervalo = max(options["poll_seconds"], 0)
        while True:
            with transaction.atomic():
                trabajo = (
                    TrabajoAnalisis.objects.select_for_update()
                    .filter(estado=TrabajoAnalisis.Estado.ENCOLADO)
                    .order_by("creado_en")
                    .first()
                )
                if trabajo is not None:
                    trabajo.estado = TrabajoAnalisis.Estado.PROCESANDO
                    trabajo.save(update_fields=["estado", "actualizado_en"])
            if trabajo is None:
                if options["once"] or intervalo == 0:
                    break
                time.sleep(intervalo)
                continue
            archivo = _managed_job_path(trabajo.archivo_path)
            if archivo is None:
                trabajo.error = "Archivo de trabajo inválido."
                trabajo.estado = TrabajoAnalisis.Estado.FALLIDO
                trabajo.save(update_fields=["error", "estado", "actualizado_en"])
                continue
            try:
                resultado = ServicioPipelineMultimodal.configurado().ejecutar(
                    archivo, trabajo.session_id
                )
                trabajo.resultado = resultado
                if resultado.get("status") == "completed":
                    trabajo.estado = TrabajoAnalisis.Estado.COMPLETADO
                else:
                    trabajo.error = str(resultado.get("error") or "El pipeline no completó el análisis.")
                    trabajo.estado = TrabajoAnalisis.Estado.FALLIDO
            except (ErrorPipelineMultimodal, OSError) as error:
                self.stderr.write(f"Pipeline job failed: {error}")
                trabajo.error = "El pipeline no pudo procesar el trabajo."
                trabajo.estado = TrabajoAnalisis.Estado.FALLIDO
            try:
                with transaction.atomic():
                    trabajo.save(update_fields=["resultado", "error", "estado", "actualizado_en"])
                    resultado_publicado = (
                        ResultadoAnalisis.objects.select_for_update()
                        .filter(session_id=trabajo.session_id)
                        .order_by("-creado_en", "-pk")
                        .first()
                    )
                    valores = {
                        "request_id": trabajo.request_id or "",
                        "estado": trabajo.estado,
                        "resultado": trabajo.resultado or {"status": "failed", "error": trabajo.error},
                    }
                    valores.update(_mlops_lineage(valores["resultado"]))
                    if resultado_publicado is None:
                        ResultadoAnalisis.objects.create(
                            session_id=trabajo.session_id,
                            **valores,
                        )
                    else:
                        for campo, valor in valores.items():
                            setattr(resultado_publicado, campo, valor)
                        resultado_publicado.save(update_fields=list(valores))
            except Exception as error:
                self.stderr.write(f"No se pudo persistir el resultado: {error}")
                TrabajoAnalisis.objects.filter(pk=trabajo.pk).update(
                    estado=TrabajoAnalisis.Estado.FALLIDO,
                    error="No se pudo persistir el resultado.",
                )
                trabajo.estado = TrabajoAnalisis.Estado.FALLIDO
                trabajo.error = "No se pudo persistir el resultado."
            if trabajo.estado == TrabajoAnalisis.Estado.COMPLETADO:
                try:
                    if archivo is not None:
                        archivo.unlink(missing_ok=True)
                except OSError:
                    self.stderr.write(f"No se pudo eliminar el archivo temporal del trabajo {trabajo.job_id}")
            procesados += 1
            if options["once"]:
                break
        self.stdout.write(self.style.SUCCESS(f"Trabajos procesados: {procesados}"))
