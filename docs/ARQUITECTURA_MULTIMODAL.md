# Endpoint HTTP multimodal

## Contrato

```http
POST /api/multimodal/analizar-video/
Content-Type: multipart/form-data
```

Campos:

- `video`: archivo `.mp4`, `.mov`, `.avi`, `.mkv` o `.webm`.
- `session_id`: opcional; si falta, el backend genera uno.

La respuesta es exactamente el JSON producido por `ml/analyze_video.py`. Los
resultados DEMUCA no se fabrican: un video sin evaluación registrada devuelve
`demuca.status = "not_available"`.

## Configuración

- `MULTIMODAL_PROJECT_ROOT`: raíz que contiene `ml/` y `dataset/`.
- `MULTIMODAL_PYTHON`: intérprete del entorno ML; por defecto `dataset/.venv/bin/python`.
- `MULTIMODAL_TIMEOUT_SECONDS`: límite de ejecución; por defecto 1800 segundos.

El archivo se guarda en un directorio temporal y se elimina al terminar. El
backend ejecuta el proceso sin shell y limita las extensiones aceptadas.

## Seguridad y operación

- En producción se requiere `MULTIMODAL_SERVICE_KEY` mediante el header
  `X-Service-Key`; en desarrollo (`DEBUG=true`) puede omitirse.
- `MULTIMODAL_MAX_UPLOAD_BYTES` limita el tamaño de entrada (por defecto 2 GiB).
- Cada respuesta incluye `X-Request-ID` para correlacionar logs y fallos.

## Cliente frontend

El helper `frontend/shared/api/multimodal.ts` expone `analizarVideoMultimodal(file, sessionId?)`.
Usa `NEXT_PUBLIC_API_URL`, conserva la respuesta JSON y propaga `statusCode` y `X-Request-ID` mediante `ErrorAnalisisMultimodal`.
