# Dominios de Negocio

A continuación se detallan las responsabilidades de cada módulo del sistema:

### 🏥 Clinical
Corazón del sistema clínico.
- **Patients:** Gestión de datos personales y estado clínico.
- **Clinical Notes:** Registro de evolución por áreas (Física, Emocional, etc.) con forzado de mayúsculas para categorías.
- **Intervention Plans:** Planificación de objetivos y pasos de tratamiento.

### 🎸 Therapeutic Sessions
Gestión del día a día de la terapia.
- **Sessions:** Registro de encuentros individuales o grupales.
- **Ciclos:** Agrupación automática de sesiones (bloques de 4) para fines administrativos y financieros.
- **Resources:** Vinculación de material digital e instrumentos utilizados.

### 💰 Finance
Módulo de recaudación y egresos.
- **Payments:** Cobro por paquetes de sesiones con lógica de **Descuentos** (fijos o porcentuales).
- **Expenses:** Registro de gastos operativos de la clínica.
- **Courses:** Gestión de inscripciones y pagos para formación externa.

### 📊 Evaluations
Datos estructurados de progreso.
- **Scales:** Soporte para subescalas (tests complejos) y listas de valores (rúbricas).
- **Forms:** Creación dinámica de preguntas y asignación de formularios a terapeutas.

### 🏢 Institutions
Estructura organizacional.
- **Institutions:** Entidades legales o convenios.
- **Groups:** Sub-agrupaciones (ej: aulas, salas o departamentos).

### 📣 Marketing
Captación de pacientes.
- **Campaigns:** Seguimiento de presupuesto y gasto por plataforma.
- **Leads:** Pipeline de prospectos desde el contacto inicial hasta la conversión.
