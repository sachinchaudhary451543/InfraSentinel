# InfraMonitor Project Structure

This repository separates production code from operational utilities, tests, documentation, and historical artifacts.

## Production code

- `main.py` — primary InfraMonitor web application entry point.
- `agent.py` — endpoint telemetry agent entry point.
- `run_portal.py` — standalone admin portal entry point.
- `web/` — Flask application, routes, templates, static assets, and services.
- `core/` — shared business logic and integrations.
- `auth/` — Entra ID and authentication flows.
- `agent/` — agent package and deployable agent assets.
- `admin_portal/` — standalone administrative portal.
- `alembic/` — database migration definitions.

## Supporting code

- `scripts/database/` — database initialization, migration, schema, and maintenance utilities.
- `scripts/diagnostics/` — startup checks and verification tools.
- `scripts/operations/` — operational maintenance and collection utilities.
- `scripts/tests/` — manual API and end-to-end checks.
- `tests/` — automated test suite.
- `tools/` — reusable developer and integration tools.

Run a utility from the repository root using module syntax, for example:

`python -m scripts.database.init_db_from_models`

## Documentation and archives

- `docs/guides/` — setup, deployment, and operations guides.
- `docs/reference/` — API and feature references.
- `docs/architecture/` — architecture and implementation notes.
- `docs/reports/` — historical project reports.
- `archive/ui/` — historical HTML captures, not used by the application.

## Runtime data

- `data/` — local runtime data; database and screenshot contents are ignored by Git.
- `uploads/` — uploaded runtime files; ignored by Git.
- `instance/` — Flask runtime configuration; ignored by Git.

## Repository root policy

Keep only entry points, production packages, deployment/configuration files, and top-level project metadata at the repository root. Put new one-off scripts in the applicable `scripts/` category and new documentation in `docs/`.
