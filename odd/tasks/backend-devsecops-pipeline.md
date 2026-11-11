# Backend DevSecOps pipeline

Objective: add staged security and quality gates to the Django backend without changing the current SSH deployment provider.
Branch: `feat/project-hardening`
Delivery: one workflow slice, preserving existing deployment behavior.
Test runner: GitHub Actions workflow validation plus local YAML/readback checks.

## Specs

### S1 — Quality and tests
The backend pipeline must validate Python syntax, Django configuration, migrations, lint, tests, and coverage before deployment.

### S2 — Security gates
The backend pipeline must scan secrets, Python dependencies, source code, and Docker configuration, publishing reports without exposing credentials.

### S3 — Safe promotion
Deployment must run only after required checks pass, preserve the current SSH provider, and perform a post-deploy health check when configured.

### S4 — Least privilege
Workflow permissions must be scoped to the jobs that need them and deployment credentials must not be available to pull requests.

## Tasks

- T1 — S1-S4 — inline — completed — follow-up commit pending

## Log

- L1: User requested backend DevSecOps pipelines based on the supplied reusable workflow example.
- L2: Implementation preserves the repository's current SSH deployment instead of switching providers without explicit confirmation.
- L3: Added fast checks, Gitleaks, CodeQL, pip-audit, Trivy filesystem and image gates, PostgreSQL tests with coverage, optional SonarQube, Docker image validation, protected production deployment, pinned SSH known hosts, and optional health verification.
- L4: The pipeline intentionally keeps Python 3.12 for CI while the existing Dockerfile remains Python 3.11; runtime alignment is a follow-up decision before production promotion.
- L5: Added optional SBOM generation, configurable coverage threshold, Dependabot coverage for pip/actions/docker, staging-only ZAP baseline scanning, and optional k6 execution without changing the current SSH deployment provider.
- L6: Replaced the single-stage Dockerfile with a Python 3.12 multi-stage build, removed SSH/build tools from runtime, added a non-root `app` user, collected static assets during build, and omitted the duplicate OpenCV headless wheel from the final image.
