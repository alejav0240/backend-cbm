
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
        self._seen_cis = set()  # rastrear CIs ya usados para detectar duplicados legacy

    def import_patients(self, rows: List[List[str]], users_by_name: Dict[str, User], default_therapist: User) -> Tuple[Dict[int, Patient], Dict[int, dict]]:
        """
        Importa pacientes y sus notas clínicas.
        """
        self.patients_by_legacy_client = {}
        self.info_map = {}
        self.stats = {'patients': 0, 'notes': 0}
        self._seen_cis = set()

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

    # CIs que son placeholders conocidos en el sistema legacy
    PLACEHOLDER_CIS = {"0", "0000", "000", "1234"}

    def _resolve_patient_ci(self, raw_ci, legacy_client_id, first_name, last_name):
        ci_candidate = self._limit_text(raw_ci, 30)
        if not raw_ci or raw_ci in self.PLACEHOLDER_CIS:
            return self._limit_text(f"LEGACY-PAT-{legacy_client_id}", 30)
        if ci_candidate in self._seen_cis:
            ci = self._limit_text(f"LEGACY-PAT-{legacy_client_id}", 30)
            self.logger(f"⚠️ CI duplicado '{raw_ci}' para cliente id={legacy_client_id} ({first_name} {last_name}) → usando {ci}")
        else:
            ci = ci_candidate
        self._seen_cis.add(ci_candidate)
        return ci

    def _patient_values(self, row, legacy_client_id):
        first_name = self._limit_text(self._clean_text(row[1]), 100)
        last_name = self._limit_text(self._clean_text(row[2]), 100)
        ci = self._resolve_patient_ci(self._clean_text(row[3]), legacy_client_id, first_name, last_name)
        return {
            "first_name": first_name, "last_name": last_name, "ci": ci,
            "birth_date": self._to_date(row[4]), "image_url": self._clean_text(row[5]) or None,
            "notes": self._clean_text(row[6]), "diagnosis": self._limit_text(self._clean_text(row[7]), 50),
            "residence": self._limit_text(self._clean_text(row[8]), 100),
            "tutor_fullname": self._clean_text(row[9]),
            "clinical": {
                "GENERAL_OBJECTIVE": self._clean_text(row[12]), "SOCIAL_AREA": self._clean_text(row[13]),
                "COGNITIVE_AREA": self._clean_text(row[14]), "PHYSICAL_AREA": self._clean_text(row[15]),
                "EMOTIONAL_AREA": self._clean_text(row[16]), "METHODS": self._clean_text(row[17]),
                "ADDITIONAL_NOTES": self._clean_text(row[18]),
            },
        }

    def _save_patient(self, values, created_at):
        if self.dry_run:
            return Patient(ci=values["ci"], first_name=values["first_name"], last_name=values["last_name"], created_at=created_at)
        patient, created = Patient.objects.update_or_create(
            ci=values["ci"],
            defaults={key: values[key] for key in ("first_name", "last_name", "birth_date", "image_url", "diagnosis", "residence", "notes")}
            | {"status": Patient.Status.ACTIVE, "registration_complete": True},
        )
        if created or patient.created_at != created_at:
            Patient.objects.filter(pk=patient.pk).update(created_at=created_at)
            patient.refresh_from_db()
        return patient

    def _save_clinical_notes(self, patient, therapist, clinical):
        if self.dry_run:
            self.stats["notes"] += sum(bool(value) for value in clinical.values())
            return
        for category, content in clinical.items():
            self._upsert_clinical_note(patient, therapist, category, content)

    def _process_row(self, row, users_by_name, default_therapist):
        legacy_client_id = self._to_int(row[0])
        values = self._patient_values(row, legacy_client_id)
        legacy_info_id = self._to_int(row[19]) if len(row) > 19 else None
        # Si el cliente no tiene infocliente (LEFT JOIN devuelve NULL), usar client_id como clave
        # con signo negativo para no colisionar con ids reales de infoclientes
        if legacy_info_id is None:
            legacy_info_id = -legacy_client_id
            self.logger(f"⚠️  Cliente id={legacy_client_id} ({first_name} {last_name}) sin infocliente → info_map key={legacy_info_id}")
        created_at = self._to_datetime(row[20]) if len(row) > 20 else timezone.now()
        patient = self._save_patient(values, created_at)
        
        self.patients_by_legacy_client[legacy_client_id] = patient
        self.stats['patients'] += 1

        # Resolver tutor
        tutor_user = self._resolve_or_create_tutor_user(legacy_info_id, values["tutor_fullname"], users_by_name)
        
        if not self.dry_run:
            patient.tutor = tutor_user
            patient.save(update_fields=["tutor", "updated_at"])

        self._save_clinical_notes(patient, default_therapist, values["clinical"])

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
