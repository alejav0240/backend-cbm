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
