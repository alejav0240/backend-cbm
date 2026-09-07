import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def send_welcome_credentials_email(user, plain_password: str) -> bool:
    """
    Envía un correo de bienvenida con las credenciales de acceso al usuario recién registrado.
    Retorna True si el envío fue exitoso, o False si ocurrió algún error (sin interrumpir la creación del usuario).
    """
    if not user.email:
        logger.warning(f"No se pudo enviar correo de bienvenida: el usuario {user.username} no tiene email.")
        return False

    try:
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
        login_url = f"{frontend_url}/login"
        full_name = f"{user.first_name} {user.last_name}".strip() or user.username

        context = {
            "user": user,
            "full_name": full_name,
            "username": user.username,
            "plain_password": plain_password,
            "login_url": login_url,
        }

        subject = "Bienvenido a la Plataforma CBM - Credenciales de Acceso"
        from_email = getattr(
            settings,
            "DEFAULT_FROM_EMAIL",
            "Centro Boliviano de Musicoterapia <soporte@musicoterapiabolivia.com>",
        )
        to_email = [user.email]

        # Renderizar plantilla HTML
        html_content = render_to_string("emails/welcome_credentials.html", context)
        text_content = strip_tags(html_content)

        # Crear y enviar mensaje multiparte (HTML y texto plano de respaldo)
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=to_email,
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)

        logger.info(f"Correo de bienvenida enviado exitosamente a {user.email} (usuario: {user.username}).")
        return True

    except Exception as exc:
        logger.error(
            f"Error al enviar correo de bienvenida con credenciales a {user.email}: {exc}",
            exc_info=True,
        )
        return False
