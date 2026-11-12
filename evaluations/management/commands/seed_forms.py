from django.core.management.base import BaseCommand
from django.db import transaction

FORM_REFERENCIAS_MUSICALES = 'Referencias Musicales'
FORM_REFERENCIAS_GENERALES = 'Referencias Generales'
FORM_REFERENCIAS_FAMILIARES = 'Referencias Familiares'

from evaluations.models import Form, FormQuestion


CUESTIONARIO_INGRESO = {
    "id": 1,
    "name": "Cuestionario de Ingreso",
    "description": (
        "Formulario de ingreso con referencias musicales, generales y familiares. "
        "Completado por los responsables del paciente."
    ),
    "questions": [
        # ── Referencias Musicales ─────────────────────────────────────────────
        {
            "order_index": 1,
            "section": FORM_REFERENCIAS_MUSICALES,
            "question": "¿Cuáles son las preferencias/rechazos musicales/sonoros de los responsables?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
        {
            "order_index": 2,
            "section": FORM_REFERENCIAS_MUSICALES,
            "question": "¿Cuáles/Cómo fueron tus experiencias musicales/sonoras durante el embarazo?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
        {
            "order_index": 3,
            "section": FORM_REFERENCIAS_MUSICALES,
            "question": "¿Cuáles/Cómo fueron tus primeras experiencias musicales/sonoras después del nacimiento?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
        {
            "order_index": 4,
            "section": FORM_REFERENCIAS_MUSICALES,
            "question": "¿Cuáles son las preferencias/rechazos musicales/sonoros del niño?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
        {
            "order_index": 5,
            "section": FORM_REFERENCIAS_MUSICALES,
            "question": "¿Tienes experiencia musical?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
        {
            "order_index": 6,
            "section": FORM_REFERENCIAS_MUSICALES,
            "question": "¿Tienes familiares que sean músicos?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
        {
            "order_index": 7,
            "section": FORM_REFERENCIAS_MUSICALES,
            "question": "¿Tienes instrumentos musicales en casa?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
        {
            "order_index": 8,
            "section": FORM_REFERENCIAS_MUSICALES,
            "question": "¿Cómo se involucra musicalmente 'más'?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
        # ── Referencias Generales ─────────────────────────────────────────────
        {
            "order_index": 9,
            "section": FORM_REFERENCIAS_GENERALES,
            "question": "¿Tiene alguna discapacidad o enfermedad? ¿Alguna hiper o hiposensibilidad?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
        {
            "order_index": 10,
            "section": FORM_REFERENCIAS_GENERALES,
            "question": "¿Usas algún medicamento?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
        {
            "order_index": 11,
            "section": FORM_REFERENCIAS_GENERALES,
            "question": "¿Tiene algún tipo de alergia?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
        {
            "order_index": 12,
            "section": FORM_REFERENCIAS_GENERALES,
            "question": "¿Tiene alguna dificultad motora, social, comunicativa, cognitiva, emocional o de otro tipo?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
        {
            "order_index": 13,
            "section": FORM_REFERENCIAS_GENERALES,
            "question": "¿Realiza intervenciones/monitoreos/terapias?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
        {
            "order_index": 14,
            "section": FORM_REFERENCIAS_GENERALES,
            "question": "¿Tienes algún hiperenfoque?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
        # ── Referencias Familiares ────────────────────────────────────────────
        {
            "order_index": 15,
            "section": FORM_REFERENCIAS_FAMILIARES,
            "question": "¿Cuál es el origen de la familia?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
        {
            "order_index": 16,
            "section": FORM_REFERENCIAS_FAMILIARES,
            "question": "¿Tienes hermanos?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
        {
            "order_index": 17,
            "section": FORM_REFERENCIAS_FAMILIARES,
            "question": "¿Adopción u otra información relevante?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
        {
            "order_index": 18,
            "section": FORM_REFERENCIAS_FAMILIARES,
            "question": "¿Con quién pasa el niño la mayor parte del tiempo?",
            "question_type": FormQuestion.QuestionType.TEXT_LONG,
            "is_required": False,
        },
    ],
}


class Command(BaseCommand):
    help = "Crea o actualiza el Cuestionario de Ingreso (id=1) con sus 18 preguntas."

    def handle(self, *args, **options):
        self.stdout.write("Seeding formulario de ingreso...")

        with transaction.atomic():
            data = CUESTIONARIO_INGRESO

            form, created = Form.objects.update_or_create(
                id=data["id"],
                defaults={
                    "name": data["name"],
                    "description": data["description"],
                },
            )
            action = "Creado" if created else "Actualizado"
            self.stdout.write(f"  {action} Form id={form.id}: {form.name}")

            created_count = 0
            updated_count = 0

            for q_data in data["questions"]:
                # El texto completo de la pregunta incluye la sección como prefijo
                # para que el frontend pueda agruparlas visualmente si lo necesita.
                full_question = f"{q_data['question']}"

                _, q_created = FormQuestion.objects.update_or_create(
                    form=form,
                    order_index=q_data["order_index"],
                    defaults={
                        "question": full_question,
                        "question_type": q_data["question_type"],
                        "is_required": q_data["is_required"],
                    },
                )
                if q_created:
                    created_count += 1
                else:
                    updated_count += 1

            # Eliminar preguntas huérfanas con order_index fuera del rango definido
            defined_orders = {q["order_index"] for q in data["questions"]}
            orphans = FormQuestion.objects.filter(form=form).exclude(order_index__in=defined_orders)
            orphan_count = orphans.count()
            if orphan_count:
                orphans.delete()
                self.stdout.write(
                    self.style.WARNING(f"  Eliminadas {orphan_count} preguntas huérfanas.")
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f"  Preguntas: {created_count} creadas, {updated_count} actualizadas. "
                    f"Total={FormQuestion.objects.filter(form=form).count()}"
                )
            )

        self.stdout.write(self.style.SUCCESS("✅ Formulario de ingreso seeded correctamente."))
