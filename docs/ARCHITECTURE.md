# Arquitectura del Sistema - CBM Plataform

Este backend está construido con **Django 5.0+** y **Graphene-Django**, siguiendo una arquitectura modular diseñada para la escalabilidad y el mantenimiento limpio.

## Estructura de Capas

El proyecto utiliza un patrón de **Schema Splitting**. Cada aplicación de Django es responsable de su propio dominio y expone sus tipos, consultas y mutaciones de forma independiente.

```text
app/
├── models.py      # Definición de datos (PostgreSQL)
├── type.py        # Tipos de Graphene (DjangoObjectType)
├── queries.py     # Lógica de lectura (Resolvers)
├── mutations.py   # Lógica de escritura (Business Logic)
└── schema.py      # Orquestador de la app
```

## Orquestación Central
El archivo `config/schema.py` actúa como el punto de entrada único, heredando todas las `Query` y `Mutation` de las aplicaciones registradas. Esto permite que el frontend tenga un único endpoint (`/graphql/`) pero con una lógica totalmente modular.

## Optimización de Rendimiento
Para evitar el problema de **N+1** en GraphQL, el sistema utiliza de forma extensiva:
- `select_related`: Para relaciones ForeignKey (ej: Patient -> Tutor).
- `prefetch_related`: Para relaciones ManyToMany o reversas (ej: Session -> Resources).

## Base de Datos
- **Motor:** PostgreSQL.
- **Convención:** Todas las tablas usan nombres en plural personalizados mediante la propiedad `db_table` en los modelos (ej: `db_table = "patients"`).
