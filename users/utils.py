import re
import random
import unicodedata
from django.contrib.auth import get_user_model


def clean_text(text: str) -> str:
    """
    Normaliza el texto eliminando acentos/diacríticos y caracteres especiales,
    retornando solo letras y dígitos en mayúsculas.
    """
    if not text:
        return ""
    nfkd_form = unicodedata.normalize("NFKD", text)
    only_ascii = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    return re.sub(r"[^a-zA-Z0-9]", "", only_ascii).upper()


def generate_unique_username(first_name: str = "", last_name: str = "", digits_length: int = 3) -> str:
    """
    Genera un username corto, fácil y único en el formato:
    <3 letras primer nombre><4 letras primer apellido><combinación numérica>
    Ejemplo: Alejandro Chipana -> ALECHIP382

    Garantiza unicidad consultando el modelo User.
    """
    User = get_user_model()

    first_word = first_name.strip().split()[0] if first_name.strip() else ""
    last_word = last_name.strip().split()[0] if last_name.strip() else ""

    fn_clean = clean_text(first_word)
    ln_clean = clean_text(last_word)

    fn_part = fn_clean[:3]
    ln_part = ln_clean[:4]

    base = f"{fn_part}{ln_part}"
    if not base:
        base = "USER"
    elif len(base) < 4:
        full_clean = clean_text(f"{first_name}{last_name}")
        base = full_clean[:6] or base

    min_val = 10 ** (digits_length - 1)
    max_val = (10 ** digits_length) - 1

    # Intentar hasta 50 combinaciones numéricas aleatorias
    for _ in range(50):
        num = random.randint(min_val, max_val)
        candidate = f"{base}{num}"
        if not User.objects.filter(username=candidate).exists():
            return candidate

    # Si hay muchas colisiones, buscar secuencialmente
    counter = min_val
    while User.objects.filter(username=f"{base}{counter}").exists():
        counter += 1
    return f"{base}{counter}"
