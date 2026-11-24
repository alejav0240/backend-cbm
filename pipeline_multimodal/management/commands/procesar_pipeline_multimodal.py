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


def _claim_next_job():
    with transaction.atomic():
        job = (
            TrabajoAnalisis.objects.select_for_update()
            .filter(estado=TrabajoAnalisis.Estado.ENCOLADO)
            .order_by("creado_en")
            .first()
        )
        if job is not None:
            job.estado = TrabajoAnalisis.Estado.PROCESANDO
            job.save(update_fields=["estado", "actualizado_en"])
        return job


def _execute_job(job, stderr):
    archivo = _managed_job_path(job.archivo_path)
    if archivo is None:
        job.error = "Archivo de trabajo inválido."
        job.estado = TrabajoAnalisis.Estado.FALLIDO
        job.save(update_fields=["error", "estado", "actualizado_en"])
        return None
    try:
        resultado = ServicioPipelineMultimodal.configurado().ejecutar(archivo, job.session_id)
        job.resultado = resultado
        if resultado.get("status") == "completed":
            job.estado = TrabajoAnalisis.Estado.COMPLETADO
        else:
            job.error = str(resultado.get("error") or "El pipeline no completó el análisis.")
            job.estado = TrabajoAnalisis.Estado.FALLIDO
    except (ErrorPipelineMultimodal, OSError) as error:
        stderr.write(f"Pipeline job failed: {error}")
        job.error = "El pipeline no pudo procesar el trabajo."
        job.estado = TrabajoAnalisis.Estado.FALLIDO
    return archivo


def _publish_result(job):
    with transaction.atomic():
        job.save(update_fields=["resultado", "error", "estado", "actualizado_en"])
        published = (
            ResultadoAnalisis.objects.select_for_update()
            .filter(session_id=job.session_id)
            .order_by("-creado_en", "-pk")
            .first()
        )
        values = {
            "request_id": job.request_id or "",
            "estado": job.estado,
            "resultado": job.resultado or {"status": "failed", "error": job.error},
        }
        values.update(_mlops_lineage(values["resultado"]))
        if published is None:
            ResultadoAnalisis.objects.create(session_id=job.session_id, **values)
        else:
            for field, value in values.items():
                setattr(published, field, value)
            published.save(update_fields=list(values))


def _mark_persistence_failure(job):
    TrabajoAnalisis.objects.filter(pk=job.pk).update(
        estado=TrabajoAnalisis.Estado.FALLIDO, error="No se pudo persistir el resultado."
    )
    job.estado = TrabajoAnalisis.Estado.FALLIDO
    job.error = "No se pudo persistir el resultado."


def _cleanup_job_file(archivo, job, stderr):
    if archivo is None or job.estado != TrabajoAnalisis.Estado.COMPLETADO:
        return
    try:
        archivo.unlink(missing_ok=True)
    except OSError:
        stderr.write(f"No se pudo eliminar el archivo temporal del trabajo {job.job_id}")


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

    def _process_job(self, trabajo):
        archivo = _execute_job(trabajo, self.stderr)
        if archivo is None:
            return
        try:
            _publish_result(trabajo)
        except Exception as error:
            self.stderr.write(f"No se pudo persistir el resultado: {error}")
            _mark_persistence_failure(trabajo)
        _cleanup_job_file(archivo, trabajo, self.stderr)

    def handle(self, *args, **options):
        procesados = 0
        intervalo = max(options["poll_seconds"], 0)
        while True:
            trabajo = _claim_next_job()
            if trabajo is None:
                if options["once"] or intervalo == 0:
                    break
                time.sleep(intervalo)
                continue
            self._process_job(trabajo)
            procesados += 1
            if options["once"]:
                break
        self.stdout.write(self.style.SUCCESS(f"Trabajos procesados: {procesados}"))
