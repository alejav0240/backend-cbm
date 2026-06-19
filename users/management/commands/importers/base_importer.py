
import html
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

class BaseImporter:
    """
    Clase base para todos los importadores con utilidades comunes.
    """
    
    NULL_TOKENS = {"", "null", "none", "nil", "n/a", "na", "0"}
    TAG_RE = re.compile(r"<[^>]+>")
    SPACE_RE = re.compile(r"\s+")

    def __init__(self, logger=None, dry_run=False):
        self.logger = logger or self._default_logger
        self.dry_run = dry_run

    def _default_logger(self, message, style=None):
        print(message)

    def _clean_text(self, value: any) -> str:
        if value is None:
            return ""

        raw = str(value).strip()
        if raw.lower() in self.NULL_TOKENS:
            return ""

        # Convierte html a texto plano
        raw = re.sub(r"<(br|/p|/div|/li|/tr)>", "\n", raw, flags=re.IGNORECASE)
        raw = self.TAG_RE.sub(" ", raw)
        raw = html.unescape(raw)
        raw = raw.replace("\xa0", " ")

        lines = [self.SPACE_RE.sub(" ", line).strip() for line in raw.splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines)

    def _to_int(self, value: any, default=None) -> Optional[int]:
        cleaned = self._clean_text(value)
        if not cleaned:
            return default
        try:
            return int(float(cleaned))
        except (TypeError, ValueError):
            return default

    def _to_decimal(self, value: any, default=Decimal("0")) -> Decimal:
        cleaned = self._clean_text(value)
        if not cleaned:
            return default
        cleaned = cleaned.replace(",", ".")
        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return default

    def _to_date(self, value: any):
        cleaned = self._clean_text(value)
        if not cleaned:
            return None

        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(cleaned, fmt).date()
            except ValueError:
                continue
        return None

    def _to_datetime(self, value: any):
        cleaned = self._clean_text(value)
        if not cleaned:
            return None

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
            try:
                dt = datetime.strptime(cleaned, fmt)
                from django.utils import timezone
                return timezone.make_aware(dt)
            except ValueError:
                continue
        return None

    def _limit_text(self, value: any, max_length: int) -> str:
        if value is None:
            return ""
        text = str(value)
        if len(text) <= max_length:
            return text
        return text[:max_length]

    def _normalize_name(self, value: any) -> str:
        return self.SPACE_RE.sub(" ", self._clean_text(value).lower()).strip()
