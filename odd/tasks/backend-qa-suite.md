# Backend QA Suite
Objective: Add layered Django and GraphQL tests for the backend without changing production behavior.
Branch: `feat/project-hardening` | Delivery: `ask-on-risk` | Runner: `python manage.py test`

## Specs

### S1 — Unit tests for models and services
User requirement: "Pruebas Unitarias (Unit Tests)"
Acceptance: "Verificar restricciones de base de datos (unique, blank=False, foreign keys)." and "Probar métodos personalizados, propiedades y signals."
Checks: model validation/constraints, custom methods, properties, signals, and isolated service tests with mocks.

### S2 — GraphQL integration and authorization tests
User requirement: "Pruebas de integración y de Capa GraphQL"
Acceptance: "Enviar consultas válidas y verificar que la estructura y los datos devueltos coincidan con lo esperado."; "Probar filtros complejos, paginación (ej. conexiones Relay) y ordenamiento."; "Probar la creación, actualización y eliminación de registros."; "Validar que los errores de validación de negocio devuelvan mensajes claros en la respuesta de GraphQL (no errores 500 genéricos)."
Checks: representative queries/mutations, validation errors, anonymous access, RBAC, ownership, staff, and superuser paths.

### S3 — Query-count and load-test scaffolding
User requirement: "Pruebas de rendimiento y optimización (El talón de Aquiles de GraphQL)"
Acceptance: "Asegúrate de usar herramientas como assertNumQueries en tus tests para verificar que una consulta compleja no dispare decenas de queries innecesarias." and "Pruebas de Carga (Load Testing): Herramientas como Locust o k6"
Checks: bounded `assertNumQueries` tests for nested GraphQL paths and documented Locust/k6 scenario scaffolding that does not run during unit CI.

### S4 — Schema contract regression
User requirement: "Pruebas de contrato y esquema (Schema Testing)"
Acceptance: "Guardar una copia de la estructura del esquema actual y comparar el esquema generado en cada despliegue para detectar cambios destructivos, como eliminar un campo o cambiar el tipo de un dato"
Checks: deterministic schema snapshot and breaking-change test with an explicit update command.

## Tasks
- T1 [S1] inline — Add shared test factories/helpers and model/service unit coverage. Status: complete. Commit: pending.
- T2 [S2] inline — Add GraphQL query, mutation, auth, RBAC, and validation integration coverage. Status: complete. Commit: pending.
- T3 [S3] inline — Add query-count assertions and load-test scaffold/documentation. Status: complete. Commit: pending.
- T4 [S4] inline — Add schema snapshot and contract regression coverage. Status: pending. Commit: TBD.
- T5 [S1-S4] inline — Expand test runner/CI discovery and execute available verification. Status: pending. Commit: TBD.

## Log

### L1 — Original request
"asume el rol de QA experto en Django y arma estos test para todo el backend\n1. Pruebas Unitarias (Unit Tests)\nSe centran en probar componentes individuales de forma aislada (funciones, métodos, clases) utilizando herramientas como pytest o el framework nativo de pruebas de Django (django.test).\n\nModelos y Validaciones (models.py):\n\nVerificar restricciones de base de datos (unique, blank=False, foreign keys).\n\nProbar métodos personalizados, propiedades y signals.\n\nServicios y Lógica de Negocio:\n\nSi tienes lógica separada en archivos de servicios o utilidades (cálculos, integraciones con pasarelas de pago, procesamiento de archivos), pruébala con datos simulados (mocks).\n\n2. Pruebas de Integración y de Capa GraphQL\nAquí evalúas cómo interactúan Django y GraphQL (Graphene-Django u otra librería equivalente). Debes comprobar que las consultas (Queries), mutaciones (Mutations) y suscripciones (Subscriptions) funcionen correctamente conectadas a la base de datos.\n\nPruebas de Queries:\n\nEnviar consultas válidas y verificar que la estructura y los datos devueltos coincidan con lo esperado.\n\nProbar filtros complejos, paginación (ej. conexiones Relay) y ordenamiento.\n\nPruebas de Mutations (Escritura):\n\nProbar la creación, actualización y eliminación de registros.\n\nValidar que los errores de validación de negocio devuelvan mensajes claros en la respuesta de GraphQL (no errores 500 genéricos).\n\nPruebas de Autenticación y Autorización (Permisos):\n\nComprobar que los usuarios no autenticados no puedan acceder a campos o mutaciones protegidas.\n\nVerificar control de acceso basado en roles (RBAC) o permisos a nivel de campo/objeto.\n\n3. Pruebas de Rendimiento y Optimización (El talón de Aquiles de GraphQL)\nGraphQL permite a los clientes solicitar estructuras de datos anidadas muy complejas, lo que puede provocar el infame problema de N+1 queries (ejecutar una consulta a la base de datos por cada elemento relacionado).\n\nPruebas con django-debug-toolbar o contadores de consultas:\n\nAsegúrate de usar herramientas como assertNumQueries en tus tests para verificar que una consulta compleja no dispare decenas de queries innecesarias.\n\nUtiliza los decoradores o métodos de optimización como .select_related() y .prefetch_related() (o librerías de ayuda como graphene-django-optimizer).\n\nPruebas de Carga (Load Testing):\n\nHerramientas como Locust o k6 para simular tráfico concurrente en el punto de entrada de GraphQL y medir los tiempos de respuesta bajo estrés.\n\n4. Pruebas de Contrato y Esquema (Schema Testing)\nDado que GraphQL expone un esquema tipado estricto (schema.graphql o el esquema introspectivo), es vital evitar cambios accidentales que rompan a los clientes (Frontend).\n\nPruebas de Regresión del Esquema:\n\nGuardar una copia de la estructura del esquema actual y comparar el esquema generado en cada despliegue para detectar cambios destructivos (breaking changes), como eliminar un campo o cambiar el tipo de un dato"

### L2 — Exploration evidence
- Existing tests cover several domain and security paths, but shared factories, schema snapshotting, query-count coverage, and load-test scaffolding are missing.
- CI runs `python manage.py test --verbosity=2`; Django is not installed in the current execution environment.
- Existing working-tree changes must remain outside these QA commits unless explicitly requested later.

### L3 — Verification evidence
- Focused QA suite: `./venv/bin/python manage.py test config.test_qa_model_contracts config.test_qa_graphql_contracts config.test_qa_services config.test_qa_query_counts config.test_qa_schema_contract --noinput` — 16 tests passed.
- Full Django suite: `./venv/bin/python manage.py test --noinput` — 29 tests passed.
- App runner: `./run_tests.sh` — all listed app suites passed, including 21 tests for `config` and 20 for `pipeline_multimodal`.
- Syntax checks: `./venv/bin/python -m py_compile ...` — passed for QA tests and Locust scaffold.
- The expected Django request log for the existing `db down` regression test remains non-failing; the suite reports OK.
