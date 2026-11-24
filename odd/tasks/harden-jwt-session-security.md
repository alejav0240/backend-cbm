# Harden JWT session security

Objective: improve browser authentication security without replacing the existing GraphQL JWT cookie flow.
Branch: `feat/project-hardening`; delivery: reviewable work units; test runner: `python manage.py test users`.

## Specs

1. **S1 — Refresh-token lifecycle:** Rotate refresh credentials and provide server-side revocation for logout and security-sensitive account changes. Preserve the existing GraphQL mutation surface unless a compatibility change is required.
2. **S2 — CSRF/service boundary:** Keep browser CSRF protection enabled and restrict service-key CSRF bypass behavior to intended service-to-service requests.
3. **S3 — Regression coverage:** Add tests for cookie security attributes, refresh rotation/revocation, logout, and existing authentication behavior.

## Tasks

- T1 — S1, route: inline, status: complete, commit: pending
- T2 — S2, route: inline, status: complete, commit: pending
- T3 — S3, route: inline, status: complete, commit: pending

## Log

L1: User authorized implementing the previously recommended authentication/session improvements with: "hazlo".
L2: Existing evidence: GraphQL uses `django-graphql-jwt` cookies; access expiry is 5 minutes, refresh expiry is 7 days, refresh reuse is enabled, and logout currently deletes cookies without visible server-side revocation.
L3: Verification: `./venv/bin/python manage.py check` passed; `./venv/bin/python manage.py test config.tests.ServiceKeyCSRFExemptMiddlewareTests` passed (2 tests before the final hardening changes). `./venv/bin/python manage.py test users` was blocked before execution because PostgreSQL was unavailable for test database creation.
L4: Final focused verification: five middleware tests, Django system check, Python compilation, and `git diff --check` passed. Independent verifier confirmed operation selection, fragment traversal, invalid payload handling, refresh locking API compatibility, and logout test ordering. Full `users` database tests remain pending until PostgreSQL is available.
