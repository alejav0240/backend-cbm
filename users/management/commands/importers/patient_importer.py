
import secrets
from typing import Dict, List, Tuple

from django.contrib.auth.models import Group
from django.db import IntegrityError

from clinical.models import Patient, PatientClinicalNote
from users.models import User
from .base_importer import BaseImporter


class PatientImporter(BaseImporter):
    """
    Clase dedicada a la importación de pacientes y su información clínica.
    """

    def __init__(self, logger=None, dry_run=False):
        super().__init__(logger, dry_run)
        self.patients_by_legacy_client = {}
        self.info_map = {}
        self.stats = {'patients': 0, 'notes': 0}
        self._cache_groups = {}

    def import_patients(self, rows: List[List[str]], users_by_name: Dict[str, User], default_therapist: User) -> Tuple[Dict[int, Patient], Dict[int, dict]]:
        """
        Importa pacientes y sus notas clínicas.
        """
        self.patients_by_legacy_client = {}
        self.info_map = {}
        self.stats = {'patients': 0, 'notes': 0}

        total_rows = len(rows)
        self.logger(f"📥 Iniciando importación de {total_rows} pacientes...")

        for index, row in enumerate(rows, 1):
            if len(row) < 19:
                continue

            try:
                self._process_row(row, users_by_name, default_therapist)
            except Exception as e:
                self.logger(f"❌ Error procesando paciente en fila {index}: {str(e)}")

        self.logger(f"✅ Pacientes migrados: {self.stats['patients']}")
        self.logger(f"✅ Notas clínicas migradas: {self.stats['notes']}")

        return self.patients_by_legacy_client, self.info_map

    def _process_row(self, row, users_by_name, default_therapist):
        legacy_client_id = self._to_int(row[0])
        first_name = self._limit_text(self._clean_text(row[1]), 100)
        last_name = self._limit_text(self._clean_text(row[2]), 100)
        ci_raw = self._clean_text(row[3])
        ci = self._limit_text(ci_raw if ci_raw and ci_raw not in {"0", "0000"} else f"LEGACY-PAT-{legacy_client_id}", 30)
        birth_date = self._to_date(row[4])
        image_url = self._clean_text(row[5]) or None
        
        notes = self._clean_text(row[6])
        diagnosis = self._limit_text(self._clean_text(row[7]), 50)
        residence = self._limit_text(self._clean_text(row[8]), 100)
        tutor_fullname = self._clean_text(row[9])
        
        general_objective = self._clean_text(row[12])
        social = self._clean_text(row[13])
        cognitive = self._clean_text(row[14])
        physical = self._clean_text(row[15])
        emotional = self._clean_text(row[16])
        methods = self._clean_text(row[17])
        questionnaire = self._clean_text(row[18])
        
        legacy_info_id = self._to_int(row[19]) if len(row) > 19 else legacy_client_id
        created_at = self._to_datetime(row[20]) if len(row) > 20 else timezone.now()

        status = Patient.Status.ACTIVE

        if self.dry_run:
            patient = Patient(ci=ci, first_name=first_name, last_name=last_name, created_at=created_at)
        else:
            patient, created = Patient.objects.update_or_create(
                ci=ci,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "birth_date": birth_date,
                    "image_url": image_url,
                    "status": status,
                    "diagnosis": diagnosis,
                    "residence": residence,
                    "notes": notes,
                    "registration_complete": True,
                },
            )
            # Forzar la fecha de creación legacy
            if created or patient.created_at != created_at:
                Patient.objects.filter(pk=patient.pk).update(created_at=created_at)
                patient.refresh_from_db()
        
        self.patients_by_legacy_client[legacy_client_id] = patient
        self.stats['patients'] += 1

        # Resolver tutor
        tutor_user = self._resolve_or_create_tutor_user(legacy_info_id, tutor_fullname, users_by_name)
        
        if not self.dry_run:
            patient.tutor = tutor_user
            patient.save(update_fields=["tutor", "updated_at"])

            # Crear notas clínicas
            self._upsert_clinical_note(patient, default_therapist, "GENERAL_OBJECTIVE", general_objective)
            self._upsert_clinical_note(patient, default_therapist, "PHYSICAL_AREA", physical)
            self._upsert_clinical_note(patient, default_therapist, "EMOTIONAL_AREA", emotional)
            self._upsert_clinical_note(patient, default_therapist, "COGNITIVE_AREA", cognitive)
            self._upsert_clinical_note(patient, default_therapist, "SOCIAL_AREA", social)
            self._upsert_clinical_note(patient, default_therapist, "METHODS", methods)
            self._upsert_clinical_note(patient, default_therapist, "ADDITIONAL_NOTES", questionnaire)
        else:
            # En dry-run también incrementamos el contador para ver que se procesaron
            if general_objective: self.stats['notes'] += 1
            if physical: self.stats['notes'] += 1
            if emotional: self.stats['notes'] += 1
            if cognitive: self.stats['notes'] += 1
            if social: self.stats['notes'] += 1
            if methods: self.stats['notes'] += 1
            if questionnaire: self.stats['notes'] += 1

        self.info_map[legacy_info_id] = {
            "patient": patient,
            "tutor_user": tutor_user,
        }

    def _resolve_or_create_tutor_user(self, legacy_info_id, tutor_name, users_by_name):
        key = self._normalize_name(tutor_name)
        if key and key in users_by_name:
            return users_by_name[key]

        first_name, last_name = self._split_name(tutor_name)
        username = f"legacy_tutor_{legacy_info_id}"

        if self.dry_run:
            return User(username=username, first_name=first_name, last_name=last_name)

        tutor_user, created = User.objects.update_or_create(
            username=username,
            defaults={
                "first_name": self._limit_text(first_name, 150),
                "last_name": self._limit_text(last_name, 150),
                "ci": self._limit_text(f"LEGACY-TUTOR-{legacy_info_id}", 50),
                "celular": "",
                "status": "active",
                "visibility": "private",
                "is_active": True,
            },
        )
        
        if created:
            tutor_user.set_password(secrets.token_urlsafe(16))
            tutor_user.save(update_fields=["password"])

        # Asignar al grupo de tutores (group id 5)
        try:
            group_tutor = self._get_or_create_group(5, "Tutors")
            if group_tutor:
                tutor_user.groups.add(group_tutor)
        except Exception:
            pass

        users_by_name[key] = tutor_user
        return tutor_user

    def _upsert_clinical_note(self, patient, author, category, content):
        if not content:
            return

        note, created = PatientClinicalNote.objects.get_or_create(
            patient=patient,
            category=category,
            defaults={"author": author, "content": content},
        )
        if not created and note.content != content:
            note.author = author
            note.content = content
            note.save(update_fields=["author", "content"])
        self.stats['notes'] += 1

    def _split_name(self, full_name):
        name = self._clean_text(full_name)
        if not name:
            return "Tutor", "Legacy"
        chunks = name.split(" ", 1)
        if len(chunks) == 1:
            return chunks[0], "Legacy"
        return chunks[0], chunks[1]

    def _get_or_create_group(self, pk, name):
        if pk in self._cache_groups:
            return self._cache_groups[pk]
            
        grp = Group.objects.filter(pk=pk).first()
        if not grp:
            try:
                grp = Group.objects.create(id=pk, name=name)
            except IntegrityError:
                grp, _ = Group.objects.get_or_create(name=name)
        
        self._cache_groups[pk] = grp
        return grp
