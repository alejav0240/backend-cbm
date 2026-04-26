# Autenticación y Seguridad

El sistema utiliza un esquema de autenticación basado en **JWT (JSON Web Tokens)** con una implementación de máxima seguridad mediante **Cookies HttpOnly**.

## Flujo de Autenticación

1.  **Login (`token_auth`):** El usuario envía credenciales. El servidor genera un `access_token` y un `refresh_token`.
2.  **Almacenamiento:** Los tokens **no se devuelven en el cuerpo JSON** (evitando ataques XSS). Se inyectan directamente en el navegador mediante cookies con los flags `HttpOnly`, `SameSite=Lax` y `Secure` (en producción).
3.  **Persistencia:** Los `refresh_tokens` se almacenan en la base de datos (Long Running Refresh Tokens), permitiendo invalidar sesiones de forma remota si es necesario.

## Mutaciones de Seguridad
- `token_auth`: Inicia sesión y genera cookies.
- `refresh_token`: Renueva el `access_token` usando la cookie de refresco.
- `revoke_token`: Invalida un token de refresco.
- `logout`: Borra las cookies del navegador.
- `change_password`: Permite al usuario cambiar su contraseña validando la anterior.

## Configuración en Settings
La configuración central reside en `GRAPHQL_JWT` dentro de `config/settings.py`.
- `JWT_AUTH_HTTPONLY`: True.
- `JWT_COOKIE_NAME`: `access_token`.
- `JWT_REFRESH_TOKEN_COOKIE_NAME`: `refresh_token`.
