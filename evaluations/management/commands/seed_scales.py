import os

from django.core.management.base import BaseCommand
from evaluations.models import Scale, Subscale, ScaleValue
from django.db import transaction

SCALE_COMPORTAMIENTOS_RESTRICTIVOS = 'Comportamientos Restrictivos'
SCALE_INTERACCION_SOCIAL = 'Interacción Social y Cognición'
SCALE_PERCEPCION_RITMICA = 'Percepción y Exploración Rítmica'
SCALE_PERCEPCION_SONORA = 'Percepción y Exploración Sonora'
SCALE_EXPLORACION_VOCAL = 'Exploración Vocal'
SCALE_MOVIMIENTO_CORPORAL = 'Movimiento Corporal con la Música'

class Command(BaseCommand):
    help = 'Seeds the database with DEMUCA, ERI, and CIM scales.'

    def handle(self, *args, **options):
        self.stdout.write('Seeding scales...')
        demuca_max_value = int(os.getenv('DEMUCA_MAX_VALUE', '2'))
        if demuca_max_value not in (2, 3):
            raise ValueError('DEMUCA_MAX_VALUE must be 2 or 3')
        
        with transaction.atomic():
            # 1. Escala DEMUCA
            demuca, _ = Scale.objects.update_or_create(
                id=1,
                defaults={
                    'name': 'Escala DEMUCA',
                    'description': 'Escala de Desenvolvimento Musical de Crianças com Autismo',
                    'scale_type': Scale.ScaleType.SUBSCALE
                }
            )

            # Subscales for DEMUCA
            subscales_data = [
                # CATEGORÍA I: Comportamientos Restrictivos
                (1, 'Estereotipias', 'Conductas motoras o verbales repetitivas sin relación con el contexto.', demuca_max_value, 'Comportamientos Restrictivos'),
                (2, 'Agresividad', 'Conductas hostiles, destructivas o autoagresivas.', demuca_max_value, 'Comportamientos Restrictivos'),
                (3, 'Desinterés', 'Indiferencia o falta de esfuerzo para participar en actividades musicales.', demuca_max_value, 'Comportamientos Restrictivos'),
                (4, 'Pasividad', 'Participación sin iniciativa propia.', demuca_max_value, 'Comportamientos Restrictivos'),
                (5, 'Resistencia', 'Oposición activa a cambios o actividades.', demuca_max_value, 'Comportamientos Restrictivos'),
                (6, 'Reclusión / Aislamiento', 'Retiro voluntario de la interacción social.', demuca_max_value, 'Comportamientos Restrictivos'),
                (7, 'Berrinche', 'Explosiones emocionales con finalidad oposicionista.', demuca_max_value, 'Comportamientos Restrictivos'),
                
                # CATEGORÍA II: Interacción Social y Cognición
                (8, 'Contacto Visual', 'Mantener la mirada dirigida hacia otra persona durante la interacción.', demuca_max_value, 'Interacción Social y Cognición'),
                (9, 'Comunicación Verbal', 'Utilización de palabras para comprender o expresar mensajes.', demuca_max_value, 'Interacción Social y Cognición'),
                (10, 'Interacción con Instrumentos', 'Iniciar o mantener actividades con instrumentos musicales.', demuca_max_value, 'Interacción Social y Cognición'),
                (11, 'Interacción con Otros Objetos', 'Uso funcional de objetos no musicales.', demuca_max_value, 'Interacción Social y Cognición'),
                (12, 'Interacción con Educador / Musicoterapeuta', 'Participación compartida con el terapeuta.', demuca_max_value, 'Interacción Social y Cognición'),
                (13, 'Interacción con Padres', 'Participación musical conjunta con familiares presentes.', demuca_max_value, 'Interacción Social y Cognición'),
                (14, 'Interacción con Pares', 'Participación compartida con otros niños.', demuca_max_value, 'Interacción Social y Cognición'),
                (15, 'Atención', 'Capacidad de focalizar estímulos relevantes.', demuca_max_value, 'Interacción Social y Cognición'),
                (16, 'Imitación', 'Reproducción de acciones observadas en otras personas.', demuca_max_value, 'Interacción Social y Cognición'),

                # CATEGORÍA III: Percepción y Exploración Rítmica
                (17, 'Pulso Interno', 'Generación de un pulso rítmico propio y regular.', demuca_max_value, 'Percepción y Exploración Rítmica'),
                (18, 'Regulación Temporal', 'Capacidad de ajustar el propio pulso al ritmo musical externo.', demuca_max_value, 'Percepción y Exploración Rítmica'),
                (19, 'Apoyo Rítmico', 'Marcación de tiempos fuertes de la música.', demuca_max_value, 'Percepción y Exploración Rítmica'),
                (20, 'Ritmo Real', 'Reproducción de secuencias rítmicas sincronizadas.', demuca_max_value, 'Percepción y Exploración Rítmica'),
                (21, 'Contrastes de Tempo', 'Percepción de cambios de velocidad musical.', demuca_max_value, 'Percepción y Exploración Rítmica'),

                # CATEGORÍA IV: Percepción y Exploración Sonora
                (22, 'Sonido Silencio', 'Percepción de la presencia o ausencia de sonido.', demuca_max_value, 'Percepción y Exploración Sonora'),
                (23, 'Timbre', 'Diferenciación de las características sonoras de los instrumentos.', demuca_max_value, 'Percepción y Exploración Sonora'),
                (24, 'Planos de Altura', 'Percepción de sonidos graves, medios y agudos.', demuca_max_value, 'Percepción y Exploración Sonora'),
                (25, 'Movimiento Sonoro', 'Percepción de direcciones melódicas ascendentes o descendentes.', demuca_max_value, 'Percepción y Exploración Sonora'),
                (26, 'Contrastes de Intensidad', 'Percepción de cambios en el volumen sonoro.', demuca_max_value, 'Percepción y Exploración Sonora'),
                (27, 'Repetición de Ideas Rítmicas o Melódicas', 'Reconocimiento y reproducción de patrones musicales.', demuca_max_value, 'Percepción y Exploración Sonora'),
                (28, 'Sentido de Conclusión', 'Reconocimiento del final de frases o piezas musicales.', demuca_max_value, 'Percepción y Exploración Sonora'),

                # CATEGORÍA V: Exploración Vocal
                (29, 'Vocalizaciones', 'Producciones vocales dominadas por sonidos vocálicos sin articulación clara.', demuca_max_value, 'Exploración Vocal'),
                (30, 'Balbuceos', 'Producciones vocales compuestas principalmente por consonantes y sílabas sin significado lingüístico.', demuca_max_value, 'Exploración Vocal'),
                (31, 'Sílabas Canónicas', 'Repetición de sílabas consonantevocal de forma regular.', demuca_max_value, 'Exploración Vocal'),
                (32, 'Imitación de Canciones', 'Reproducción de fragmentos melódicos o letras previamente escuchadas.', demuca_max_value, 'Exploración Vocal'),
                (33, 'Creación Vocal', 'Producción espontánea de melodías o expresiones vocales originales.', demuca_max_value, 'Exploración Vocal'),

                # CATEGORÍA VI: Movimiento Corporal con la Música
                (34, 'Andar', 'Caminar siguiendo el pulso musical.', demuca_max_value, 'Movimiento Corporal con la Música'),
                (35, 'Correr', 'Desplazarse rápidamente en sincronía con la música.', demuca_max_value, 'Movimiento Corporal con la Música'),
                (36, 'Parar', 'Detener el movimiento en respuesta a cambios musicales.', demuca_max_value, 'Movimiento Corporal con la Música'),
                (37, 'Bailar', 'Mover el cuerpo de forma expresiva siguiendo la música.', demuca_max_value, 'Movimiento Corporal con la Música'),
                (38, 'Saltar', 'Elevar el cuerpo del suelo siguiendo el ritmo musical.', demuca_max_value, 'Movimiento Corporal con la Música'),
                (39, 'Gesticular', 'Realizar movimientos expresivos de brazos, manos o rostro.', demuca_max_value, 'Movimiento Corporal con la Música'),
                (40, 'Moverse en el Sitio', 'Movimiento corporal sin desplazamiento espacial.', demuca_max_value, 'Movimiento Corporal con la Música'),
            ]

            for sid, name, desc, max_val, cat in subscales_data:
                Subscale.objects.update_or_create(
                    id=sid,
                    defaults={
                        'scale': demuca,
                        'name': name,
                        'description': desc,
                        'max_value': max_val,
                        'category': cat
                    }
                )

            # 2. Escala ERI
            eri, _ = Scale.objects.update_or_create(
                id=2,
                defaults={
                    'name': 'Escala ERI',
                    'description': 'Escala de Relación Intermusicular / Desarrollo Musical',
                    'scale_type': Scale.ScaleType.VALUE_LIST
                }
            )

            eri_values = [
                (1, '1: NO LOS REGISTRA', 1),
                (2, '2: LOS REGISTRA', 2),
                (3, '3: LOS MANIPULA', 3),
                (4, '4: LOS EXPLORA', 4),
                (5, '5: PERSISTE EN LA UTILIZACIÓN', 5),
                (6, '6: REALIZA ALGUNA ACTIVIDAD A PARTIR DE ELLOS', 6),
                (7, '7: LES DA UN USO MUSICAL BREVE', 7),
                (8, '8: LES DA UN USO MUSICAL INTENCIONAL PROLONGADO', 8),
                (9, '9: LES DA UN USO MUSICAL CON UNA INTENCIÓN INTERMUSICAL', 9),
            ]

            for vid, label, val in eri_values:
                ScaleValue.objects.update_or_create(
                    id=vid,
                    defaults={
                        'scale': eri,
                        'label': label,
                        'value': val
                    }
                )

            # 3. Escala CIM
            cim, _ = Scale.objects.update_or_create(
                id=3,
                defaults={
                    'name': 'Escala CIM',
                    'description': 'Escala de Comunicación Intermusical',
                    'scale_type': Scale.ScaleType.VALUE_LIST
                }
            )

            cim_values = [
                (10, '1: SIN COMUNICACIÓN', 1),
                (11, '2: CONTACTO DE UN SOLO LADO: NO HAY RESPUESTA DEL PARTICIPANTE', 2),
                (12, '3: CONTACTO DE UN SOLO LADO: NO HAY RESPUESTA MUSICAL DEL PARTI', 3),
                (13, '4: RESPUESTA MUSICAL AUTODIRIGIDA DEL PARTICIPANTE', 4),
                (14, '5: RESPUESTA TENUE DEL PARTICIPANTE', 5),
                (15, '6: RESPUESTA MUSICALMENTE DIRIGIDA Y SOSTENIDA', 6),
                (16, '7: ESTABLECIENDO CONTACTO MUTUO', 7),
                (17, '8: EXTENDIENDO EL CONTACTO MUTUO', 8),
                (18, '9: ASOCIACIÓN MUSICAL', 9),
            ]

            for vid, label, val in cim_values:
                ScaleValue.objects.update_or_create(
                    id=vid,
                    defaults={
                        'scale': cim,
                        'label': label,
                        'value': val
                    }
                )

        self.stdout.write(self.style.SUCCESS('Successfully seeded scales!'))
