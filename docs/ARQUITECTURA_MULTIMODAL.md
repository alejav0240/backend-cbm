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

## Módulo backend

El pipeline HTTP vive en `pipeline_multimodal/`, con separación entre vista, servicio de aplicación y configuración del proceso ML. La ruta nueva es `/api/pipeline-multimodal/analizar-video/`; se conserva `/api/multimodal/analizar-video/` para compatibilidad.

## Consulta de resultados

```http
GET /api/pipeline-multimodal/resultados/{session_id}/
```

Devuelve el último JSON persistido o `202` con `status = "pending"` si todavía no existe.

## Procesamiento asíncrono de sesiones

El worker de subida del frontend envía la grabación a:

```http
POST /api/pipeline-multimodal/trabajos/
```

con `video` y `session_id`. La respuesta `202` entrega `job_id`; un trabajo
activo para la misma sesión se reutiliza para que los reintentos no dupliquen
el análisis. El estado se consulta en:

```http
GET /api/pipeline-multimodal/trabajos/{job_id}/
```

En producción debe ejecutarse un worker persistente, por ejemplo:

```bash
python manage.py procesar_pipeline_multimodal --poll-seconds 5
```

El worker toma un trabajo con bloqueo transaccional, ejecuta `ml/analyze_video.py`,
persiste el resultado y elimina el archivo temporal. `MULTIMODAL_SERVICE_KEY`
debe estar configurada tanto en backend como en el proceso servidor de Next.js;
no se expone al navegador.
