from django.db import models
from users.models import User
from django.utils import timezone

class Patient(models.Model):

    class Status(models.TextChoices):
        ACTIVE = "active", "Activo"
        INACTIVE = "inactive", "Inactivo"
        DISCHARGED = "discharged", "Alta"
        Pending = "pending", "Pendiente"

    tutor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tutored_patients",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    ci = models.CharField(max_length=30, blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)
    image_url = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    registration_complete = models.BooleanField(default=False)
    diagnosis = models.CharField(max_length=50, default='sin diagnostico')
    residence = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = "patients"

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class PatientClinicalNote(models.Model):

    class Category(models.TextChoices):
        # Iniciales que ya tenías
        DIAGNOSIS = "diagnosis", "Diagnóstico"
        GENERAL_OBJECTIVE = "general_objective", "Objetivo general"
        OBSERVATION = "observation", "Observación"

        # Los faltantes basados en tu mutación
        PHYSICAL_AREA = "physical_area", "Área Física"
        EMOTIONAL_AREA = "emotional_area", "Área Emocional"
        COGNITIVE_AREA = "cognitive_area", "Área Cognitiva"
        SOCIAL_AREA = "social_area", "Área Social"
        METHODS = "methods", "Métodos"
        ADDITIONAL_NOTES = "additional_notes", "Notas Adicionales"

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="clinical_notes")
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="authored_notes")
    category = models.CharField(max_length=30, choices=Category.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "patient_clinical_notes"
        ordering = ["-created_at"]
        unique_together = ('patient', 'category')

    def save(self, *args, **kwargs):
        # Lógica de Mutator: Siempre en mayúsculas antes de ir a la DB
        if self.category:
            self.category = self.category.upper()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_category_display()} — {self.patient} ({self.created_at.date()})"

class InterventionPlan(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="intervention_plans")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_plans")
    main_objective = models.TextField()
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(blank=True, null=True)
    progress_percent = models.PositiveSmallIntegerField(default=0)  # 0-100
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "intervention_plans"

    def __str__(self):
        return f"Plan de {self.patient} — {self.start_date}"

    def update_progress(self):
        """Calcula y actualiza el porcentaje de progreso basado en los pasos completados."""
        total_steps = self.steps.count()
        if total_steps == 0:
            new_progress = 0
        else:
            completed_steps = self.steps.filter(is_completed=True).count()
            new_progress = int((completed_steps / total_steps) * 100)
        
        if self.progress_percent != new_progress:
            self.progress_percent = new_progress
            self.save(update_fields=["progress_percent", "updated_at"])

class PlanStep(models.Model):

    class Moment(models.TextChoices):
        ABSTRACCION = "ABSTRACCIÓN", "ABSTRACCIÓN"
        ARMONICO = "ARMÓNICO", "ARMÓNICO"
        BIENVENIDA = "BIENVENIDA", "BIENVENIDA"
        DANZA_LIBRE = "DANZA LIBRE", "DANZA LIBRE"
        DESPEDIDA = "DESPEDIDA", "DESPEDIDA"
        EXPRESION_CORPORAL = "EXPRESIÓN CORPORAL", "EXPRESIÓN CORPORAL"
        ISO = "ISO", "ISO"
        MELODICO = "MELÓDICO", "MELÓDICO"
        RELAJACION = "RELAJACIÓN", "RELAJACIÓN"
        RITMICO = "RITMICO", "RITMICO"
        RITMO_Y_ESPACIO = "RITMO Y ESPACIO", "RITMO Y ESPACIO"

    class Objective(models.TextChoices):
        COMPORTAMIENTOS_RESTRICTIVOS = "COMPORTAMIENTOS RESTRICTIVOS", "COMPORTAMIENTOS RESTRICTIVOS"
        EXPLORACION_VOCAL = "EXPLORACIÓN VOCAL", "EXPLORACIÓN VOCAL"
        INTERACCION_SOCIAL_COGNITIVA = "INTERACCIÓN SOCIAL COGNITIVA", "INTERACCIÓN SOCIAL COGNITIVA"
        MOVIMIENTO_CORPORAL_CON_MUSICA = "MOVIMIENTO CORPORAL CON MÚSICA", "MOVIMIENTO CORPORAL CON MÚSICA"
        PERCEPCION_EXPLORACION_RITMICA = "PERCEPCIÓN EXPLORACIÓN RITMICA", "PERCEPCIÓN EXPLORACIÓN RITMICA"
        PERCEPCION_EXPLORACION_SONORA = "PERCEPCIÓN EXPLORACIÓN SONORA", "PERCEPCIÓN EXPLORACIÓN SONORA"

    class Focus(models.TextChoices):
        BERRINCHE = "BERRINCHE", "BERRINCHE"
        RESISTENCIA = "RESISTENCIA", "RESISTENCIA"
        AISLAMIENTO = "AISLAMIENTO", "AISLAMIENTO"
        PASIVIDAD = "PASIVIDAD", "PASIVIDAD"
        DESINTERES = "DESINTERES", "DESINTERES"
        AGRESIVIDAD = "AGRESIVIDAD", "AGRESIVIDAD"
        ESTEREOTIPIAS = "ESTEREOTIPIAS", "ESTEREOTIPIAS"
        VOCALIZACIONES = "VOCALIZACIONES", "VOCALIZACIONES"
        BALBUCEOS = "BALBUCEOS", "BALBUCEOS"
        SILABAS_CANONICAS = "SILABAS CANÓNICAS", "SILABAS CANÓNICAS"
        IMITACION_DE_CANCIONES = "IMITACIÓN DE CANCIONES", "IMITACIÓN DE CANCIONES"
        CREACION_VOCAL = "CREACIÓN VOCAL", "CREACIÓN VOCAL"
        CONTACTO_VISUAL = "CONTACTO VISUAL", "CONTACTO VISUAL"
        COMUNICACION_VERBAL = "COMUNICACIÓN VERBAL", "COMUNICACIÓN VERBAL"
        INTERACCION_CON_OBJETOS = "INTERACCIÓN CON OBJETOS", "INTERACCIÓN CON OBJETOS"
        INTERACCION_CON_INSTRUMENTOS_MUSICALES = "INTERACCIÓN CON INSTRUMENTOS MUSICALES", "INTERACCIÓN CON INSTRUMENTOS MUSICALES"
        INTERACCION_CON_EL_MUSICOTERAPEUTA = "INTERACCIÓN CON EL MUSICOTERAPEUTA", "INTERACCIÓN CON EL MUSICOTERAPEUTA"
        INTERACCION_CON_LOS_PADRES = "INTERACCIÓN CON LOS PADRES", "INTERACCIÓN CON LOS PADRES"
        INTERACCION_CON_LOS_PARES = "INTERACCIÓN CON LOS PARES", "INTERACCIÓN CON LOS PARES"
        ATENCION = "ATENCIÓN", "ATENCIÓN"
        IMITACION = "IMITACIÓN", "IMITACIÓN"
        ANDAR = "ANDAR", "ANDAR"
        CORRER = "CORRER", "CORRER"
        PARAR = "PARAR", "PARAR"
        GESTICULAR = "GESTICULAR", "GESTICULAR"
        DANZAR = "DANZAR", "DANZAR"
        MOVIMIENTO_EN_SU_LUGAR = "MOVIMIENTO EN SU LUGAR", "MOVIMIENTO EN SU LUGAR"
        SALTAR = "SALTAR", "SALTAR"
        PULSO_INTERNO = "PULSO INTERNO", "PULSO INTERNO"
        REGULACION_TEMPORAL = "REGULACIÓN TEMPORAL", "REGULACIÓN TEMPORAL"
        RITMO_REAL = "RITMO REAL", "RITMO REAL"
        APOYO = "APOYO", "APOYO"
        CONTRASTES_DE_TEMPO = "CONTRASTES DE TEMPO", "CONTRASTES DE TEMPO"
        SONIDO_SILENCIO = "SONIDO / SILENCIO", "SONIDO / SILENCIO"
        TIMBRE = "TIMBRE", "TIMBRE"
        PLANOS_DE_ALTURA = "PLANOS DE ALTURA", "PLANOS DE ALTURA"
        MOVIMIENTO_SONORO = "MOVIMIENTO SONORO", "MOVIMIENTO SONORO"
        CONTRASTES_DE_INTENSIDAD = "CONTRASTES DE INTENSIDAD", "CONTRASTES DE INTENSIDAD"
        REPETICION_DE_IDEAS_RITMICAS_MELODICAS = "REPETICIÓN DE IDEAS RITMICAS/MELODICAS", "REPETICIÓN DE IDEAS RITMICAS/MELODICAS"
        SENSACION_DE_CONCLUSION = "SENSACIÓN DE CONCLUSIÓN", "SENSACIÓN DE CONCLUSIÓN"

    class Approach(models.TextChoices):
        ACUL_E1_ABSORCION = "ACUL-E1: ABSORCIÓN", "ACUL-E1: ABSORCIÓN"
        ACUL_E2_RESPUESTA_SIN_INTENCION = "ACUL-E2: RESPUESTA SIN INTENCIÓN", "ACUL-E2: RESPUESTA SIN INTENCIÓN"
        ACUL_E3_RESPUESTA_INTENCIONADA = "ACUL-E3: RESPUESTA INTENCIONADA", "ACUL-E3: RESPUESTA INTENCIONADA"
        ASI_E6_INTROSPECCION = "ASI-E6: INTROSPECCIÓN", "ASI-E6: INTROSPECCIÓN"
        ASI_E7_COORDINACION = "ASI-E7: COORDINACIÓN", "ASI-E7: COORDINACIÓN"
        DALCROZE = "DALCROZE", "DALCROZE"
        GIM = "GIM", "GIM"
        IMI_E4_SALIENDO_DEL_EGOCENTRISMO = "IMI-E4: SALIENDO DEL EGOCENTRISMO", "IMI-E4: SALIENDO DEL EGOCENTRISMO"
        IMI_E5_CAPTANDO_EL_SENTIDO = "IMI-E5: CAPTANDO EL SENTIDO", "IMI-E5: CAPTANDO EL SENTIDO"
        MLT_GORDON = "MLT GORDON", "MLT GORDON"
        MT_CONDUCTUAL = "MT CONDUCTUAL", "MT CONDUCTUAL"
        MT_CREATIVA = "MT CREATIVA", "MT CREATIVA"
        WILLIEMS = "WILLIEMS", "WILLIEMS"

    class MltMethod(models.TextChoices):
        ACUL_E1_ABSORCION = "ACUL-E1: ABSORCIÓN", "ACUL-E1: ABSORCIÓN"
        ACUL_E2_RESPUESTA_SIN_INTENCION = "ACUL-E2: RESPUESTA SIN INTENCIÓN", "ACUL-E2: RESPUESTA SIN INTENCIÓN"
        ACUL_E3_RESPUESTA_INTENCIONADA = "ACUL-E3: RESPUESTA INTENCIONADA", "ACUL-E3: RESPUESTA INTENCIONADA"
        ASI_E6_INTROSPECCION = "ASI-E6: INTROSPECCIÓN", "ASI-E6: INTROSPECCIÓN"
        ASI_E7_COORDINACION = "ASI-E7: COORDINACIÓN", "ASI-E7: COORDINACIÓN"
        DALCROZE = "DALCROZE", "DALCROZE"
        GIM = "GIM", "GIM"
        IMI_E4_SALIENDO_DEL_EGOCENTRISMO = "IMI-E4: SALIENDO DEL EGOCENTRISMO", "IMI-E4: SALIENDO DEL EGOCENTRISMO"
        IMI_E5_CAPTANDO_EL_SENTIDO = "IMI-E5: CAPTANDO EL SENTIDO", "IMI-E5: CAPTANDO EL SENTIDO"
        MLT_GORDON = "MLT GORDON", "MLT GORDON"
        MT_CONDUCTUAL = "MT CONDUCTUAL", "MT CONDUCTUAL"
        MT_CREATIVA = "MT CREATIVA", "MT CREATIVA"
        WILLIEMS = "WILLIEMS", "WILLIEMS"

    MUSICAL_EMPHASIS_OPTIONS = (
        "ENCUADRE JAZZ", "ENCUADRE LATINO", "ENCUADRE MODAL", "ESCUCHA ACTIVA",
        "IMPR. TEMÁTICA MELÓDICA", "IMPR. TEMÁTICA RÍTMICA", "LIVE MOTIVE",
        "PATRONES RÍTMICOS", "PATRONES TONALES",
    )

    MUSICAL_RESOURCES_OPTIONS = (
        "ADIOS DO", "AGUILA ROJA MT", "BARCO DE PAPEL", "BARQUITO PEQUEÑITO AM",
        "CAPI CAPIBARA G", "CARAMELOS DE FRESA MY", "DECIDE EL USUARIO",
        "DUENDECILLO SOÑADOR FR", "EN LA GRANJA LI", "GATITO", "GUACAMOLE II",
        "HOLA CUERPO", "HOLA MUSICOS MY", "JAZZ ADIOS G", "JAZZ EN G",
        "JAZZ HOLA DO7", "LA BAMBA", "LA SOPA DO", "LA TRUCHA",
        "LECTURA DE PARTITURAS", "LISTOS YA", "ME ESCONDI AM", "MI BICI ROJA",
        "MIRA MIRA", "MOSQUITO LO", "OBJETOS SONOROS", "PIÑA Y COCO II",
        "PINGUINOS MY", "REMANDO EL RIO LO", "UNA GRAN SOPA",
        "VOY EN MOVIMIENTO", "ZAPATITOS", "ZAPATOS GIGANTES",
    )

    plan = models.ForeignKey(InterventionPlan, on_delete=models.CASCADE, related_name="steps")
    moment = models.CharField(max_length=20, choices=Moment.choices)
    duration_minutes = models.PositiveIntegerField(blank=True, null=True)
    actual_duration = models.PositiveIntegerField(blank=True, null=True)
    objective = models.CharField(max_length=255, choices=Objective.choices)
    focus = models.TextField(blank=True, null=True, choices=Focus.choices)
    musical_resources = models.TextField(blank=True, null=True)
    musical_emphasis = models.CharField(max_length=255, blank=True, null=True)
    approach = models.CharField(max_length=255, blank=True, null=True, choices=Approach.choices)
    mlt_method = models.CharField(max_length=100, blank=True, null=True, choices=MltMethod.choices)
    order_index = models.PositiveSmallIntegerField(default=0)
    is_completed = models.BooleanField(default=False)

    class Meta:
        db_table = "plan_steps"
        ordering = ["order_index"]

    def __str__(self):
        return f"{self.get_moment_display()} — {self.objective[:60]}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.plan:
            self.plan.update_progress()

    def delete(self, *args, **kwargs):
        plan = self.plan
        super().delete(*args, **kwargs)
        if plan:
            plan.update_progress()

class TherapyReport(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="therapy_reports")
    generated_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="generated_reports")
    report_url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "therapy_reports"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Reporte de {self.patient} ({self.created_at.date()})"
