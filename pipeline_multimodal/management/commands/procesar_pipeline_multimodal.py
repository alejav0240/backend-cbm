from django.core.management.base import BaseCommand
from django.db import transaction
from pathlib import Path

from pipeline_multimodal.models import TrabajoAnalisis
from pipeline_multimodal.servicios import ErrorPipelineMultimodal, ServicioPipelineMultimodal


class Command(BaseCommand):
    help = "Procesa trabajos encolados del pipeline multimodal."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Procesa un trabajo y termina.")

    def handle(self, *args, **options):
        procesados = 0
        while True:
            with transaction.atomic():
                trabajo = (
                    TrabajoAnalisis.objects.select_for_update()
                    .filter(estado=TrabajoAnalisis.Estado.ENCOLADO)
                    .order_by("creado_en")
                    .first()
                )
                if trabajo is None:
                    break
                trabajo.estado = TrabajoAnalisis.Estado.PROCESANDO
                trabajo.save(update_fields=["estado", "actualizado_en"])
            try:
                resultado = ServicioPipelineMultimodal.configurado().ejecutar(
                    Path(trabajo.archivo_path), trabajo.session_id
                )
                trabajo.resultado = resultado
                trabajo.estado = TrabajoAnalisis.Estado.COMPLETADO
            except (ErrorPipelineMultimodal, OSError) as error:
                trabajo.error = str(error)
                trabajo.estado = TrabajoAnalisis.Estado.FALLIDO
            trabajo.save(update_fields=["resultado", "error", "estado", "actualizado_en"])
            try:
                Path(trabajo.archivo_path).unlink(missing_ok=True)
            except OSError:
                self.stderr.write(f"No se pudo eliminar el archivo temporal del trabajo {trabajo.job_id}")
            procesados += 1
            if options["once"]:
                break
        self.stdout.write(self.style.SUCCESS(f"Trabajos procesados: {procesados}"))
