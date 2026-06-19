"""
Módulo para importación de usuarios desde base de datos legacy.
"""

import re
import secrets
from collections import defaultdict
from typing import Dict, List

from django.contrib.auth.models import Group
from django.db import IntegrityError
from django.utils import timezone

from users.models import User
from .base_importer import BaseImporter


class UserImporter(BaseImporter):
    """
    Clase dedicada a la importación de usuarios desde legacy.
    """
    
    # Constantes de configuración
    USERNAME_PREFIX = "legacy_user_"
    DEFAULT_PASSWORD_LENGTH = 16
    MAX_FIRST_NAME_LENGTH = 150
    MAX_LAST_NAME_LENGTH = 150
    MAX_PHONE_LENGTH = 20
    MAX_CI_LENGTH = 50
    
    # Mapeos para normalización
    STATUS_MAP = {
        'activo': 'active',
        'activo?': 'active',
        'inactivo': 'inactive',
        'inactive': 'inactive',
        'suspendido': 'inactive',
        'bloqueado': 'inactive',
        'pending': 'pending',
        'pendiente': 'pending',
    }
    
    VISIBILITY_MAP = {
        'visible': 'public',
        'si': 'public',
        'yes': 'public',
        '1': 'public',
        'true': 'public',
        'no': 'private',
        '0': 'private',
        'false': 'private',
        'invisible': 'private',
        'oculto': 'private',
    }
    
    def __init__(self, logger=None, dry_run=False):
        super().__init__(logger, dry_run)
        self.users_by_name = {}
        self.ci_counter = defaultdict(int)
        self.stats = {
            'created': 0,
            'updated': 0,
            'errors': 0,
            'skipped': 0,
        }
        self._cache_groups = {}
    
    def import_users(self, rows: List[List[str]]) -> Dict[str, User]:
        """
        Importa usuarios desde una lista de filas legacy.
        """
        self.users_by_name = {}
        self.ci_counter = defaultdict(int)
        self.stats = {'created': 0, 'updated': 0, 'errors': 0, 'skipped': 0}
        
        total_rows = len(rows)
        self.logger(f"📥 Iniciando importación de {total_rows} usuarios...")
        
        for index, row in enumerate(rows, 1):
            if index % 50 == 0:
                self.logger(f"⏳ Progreso: {index}/{total_rows} usuarios procesados")
            
            try:
                self._process_row(row, index)
            except Exception as e:
                self.stats['errors'] += 1
                self.logger(f"❌ Error en fila {index}: {str(e)}")
        
        self._log_summary()
        return self.users_by_name
    
    def _process_row(self, row: List[str], row_index: int):
        if len(row) < 8:
            self.stats['skipped'] += 1
            self.logger(f"⚠️  Fila {row_index}: longitud insuficiente ({len(row)})")
            return
        
        legacy_id = self._to_int(row[0])
        if legacy_id is None:
            self.stats['skipped'] += 1
            self.logger(f"⚠️  Fila {row_index}: ID inválido")
            return
        
        first_name = self._clean_and_validate_name(row[1], self.MAX_FIRST_NAME_LENGTH)
        last_name = self._clean_and_validate_name(row[2], self.MAX_LAST_NAME_LENGTH)
        
        if not first_name and not last_name:
            first_name = "Sin"
            last_name = "Nombre"
        elif not first_name:
            first_name = last_name or "Usuario"
        elif not last_name:
            last_name = first_name or "Legacy"
        
        if len(row) >= 12:
            phone = self._clean_and_validate_phone(row[4], self.MAX_PHONE_LENGTH)
            ci = self._clean_and_validate_ci(row[6], self.MAX_CI_LENGTH, legacy_id)
            visibility = self._normalize_value(row[7], self.VISIBILITY_MAP, 'private')
            status = self._normalize_value(row[8], self.STATUS_MAP, 'active')
            photo = self._clean_text(row[9]) or None
            created_at = self._to_datetime(row[10]) or timezone.now()
        else:
            phone = self._clean_and_validate_phone(row[4], self.MAX_PHONE_LENGTH)
            ci = self._clean_and_validate_ci(row[6], self.MAX_CI_LENGTH, legacy_id)
            visibility = 'private'
            status = 'active'
            photo = None
            created_at = timezone.now()
        
        user = self._create_or_update_user(
            legacy_id=legacy_id,
            first_name=first_name,
            last_name=last_name,
            ci=ci,
            phone=phone,
            status=status,
            visibility=visibility,
            photo=photo,
            created_at=created_at,
        )
        
        full_name_key = self._normalize_name(f"{first_name} {last_name}")
        self.users_by_name[full_name_key] = user
    
    def _create_or_update_user(self, **kwargs):
        legacy_id = kwargs['legacy_id']
        first_name = kwargs['first_name']
        last_name = kwargs['last_name']
        ci = kwargs['ci']
        phone = kwargs['phone']
        status = kwargs['status']
        visibility = kwargs['visibility']
        photo = kwargs['photo']
        created_at = kwargs.get('created_at', timezone.now())
        
        username = self._generate_unique_username(legacy_id)
        email = self._generate_email(first_name, last_name, legacy_id)
        
        if ci in self.ci_counter:
            self.ci_counter[ci] += 1
            ci = f"{ci}_{self.ci_counter[ci]}"
        else:
            self.ci_counter[ci] = 1
        
        defaults = {
            "first_name": first_name,
            "last_name": last_name,
            "ci": ci,
            "celular": phone,
            "email": email,
            "status": status,
            "visibility": visibility,
            "foto": photo,
            "is_active": True,
            "is_staff": False,
            "date_joined": created_at,
        }
        
        if self.dry_run:
            self.stats['created' if not User.objects.filter(username=username).exists() else 'updated'] += 1
            return User(username=username, **defaults)
        
        try:
            user, created = User.objects.update_or_create(
                username=username,
                defaults=defaults
            )
            
            if created:
                user.set_password(secrets.token_urlsafe(self.DEFAULT_PASSWORD_LENGTH))
                user.save(update_fields=["password"])
                self.stats['created'] += 1
            else:
                self.stats['updated'] += 1
            
            self._assign_therapist_group(user)
            return user
            
        except IntegrityError:
            alt_username = f"{username}_{secrets.token_hex(4)}"
            user, created = User.objects.update_or_create(
                username=alt_username,
                defaults=defaults
            )
            if created:
                user.set_password(secrets.token_urlsafe(self.DEFAULT_PASSWORD_LENGTH))
                user.save(update_fields=["password"])
                self.stats['created'] += 1
            return user

    def _clean_and_validate_name(self, value, max_length):
        cleaned = self._clean_text(value)
        if not cleaned:
            return ""
        cleaned = re.sub(r'[^\w\s\-áéíóúñÑ]', '', cleaned)
        return self._limit_text(cleaned, max_length)
    
    def _clean_and_validate_phone(self, value, max_length):
        cleaned = self._clean_text(value)
        if not cleaned:
            return ""
        cleaned = re.sub(r'[^\d+]', '', cleaned)
        return self._limit_text(cleaned, max_length)
    
    def _clean_and_validate_ci(self, value, max_length, legacy_id):
        cleaned = self._clean_text(value)
        if cleaned and cleaned not in {"0", "0000", "999999", "sin", "ninguno"}:
            return self._limit_text(cleaned, max_length)
        return f"LEGACY-USR-{legacy_id}"
    
    def _normalize_value(self, value, mapping, default):
        cleaned = self._clean_text(value).lower()
        return mapping.get(cleaned, default)

    def _generate_unique_username(self, legacy_id):
        base_username = f"{self.USERNAME_PREFIX}{legacy_id}"
        if not User.objects.filter(username=base_username).exists():
            return base_username
        counter = 1
        while User.objects.filter(username=f"{base_username}_{counter}").exists():
            counter += 1
        return f"{base_username}_{counter}"
    
    def _generate_email(self, first_name, last_name, legacy_id):
        clean_first = re.sub(r'[^a-zA-Z]', '', first_name.lower())
        clean_last = re.sub(r'[^a-zA-Z]', '', last_name.lower())
        base_email = f"{clean_first}.{clean_last}.{legacy_id}@legacy.com"
        if User.objects.filter(email=base_email).exists():
            return f"{clean_first}.{clean_last}.{legacy_id}.{secrets.token_hex(4)}@legacy.com"
        return base_email
    
    def _assign_therapist_group(self, user):
        if 'therapist' not in self._cache_groups:
            try:
                from django.contrib.auth.models import Group
                self._cache_groups['therapist'] = Group.objects.get_or_create(id=3, defaults={'name': 'Therapists'})[0]
            except Exception:
                self._cache_groups['therapist'] = None
        
        group = self._cache_groups['therapist']
        if group and not user.groups.filter(id=3).exists():
            try:
                user.groups.add(group)
            except Exception:
                pass
    
    def _log_summary(self):
        total = sum([self.stats['created'], self.stats['updated'], self.stats['errors'], self.stats['skipped']])
        self.logger(f"📊 RESUMEN: Total={total}, Creados={self.stats['created']}, Actualizados={self.stats['updated']}, Errores={self.stats['errors']}")
