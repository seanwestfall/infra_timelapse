# Infra Timelapse

Infra Timelapse captures repeat satellite views of strategic ports and logistics corridors. The current image fetcher reads `infra_timelapse_ports_corridors.json`; the database foundation adds a normalized PostgreSQL/PostGIS catalog without changing that runtime path yet.

## Local database

Requirements: Docker Compose and Python 3.11 or newer. A local `psql` client is optional; the database helper automatically uses the client inside the Compose service when one is not installed.

```bash
cp .env.example .env
make db-up
make db-migrate
make db-seed
make db-validate
```

The Compose service uses PostgreSQL 18 with PostGIS 3.6. Set `DATABASE_URL` to run the same commands against another PostgreSQL database with PostGIS available. Credentials belong in the environment and must not be committed.

Useful commands:

```bash
make db-health       # PostgreSQL/PostGIS extension check
make db-build-seed   # regenerate the committed v0.1 SQL seed
make db-test         # unit, migration, idempotency, invariant, and spatial tests
make db-down         # stop the local service without removing its volume
make db-reset CONFIRM_RESET=1  # remove the local volume and rebuild from zero
```

Migrations are plain SQL under `db/migrations`. `scripts/db.py` records each applied filename and SHA-256 checksum in `public.schema_migrations`; editing an applied migration is rejected.

See [`docs/database-migration-plan.md`](docs/database-migration-plan.md) for the structural, seed, and validation order. Backup and recovery responsibilities for database metadata and separately stored imagery are documented in [`docs/database-backup.md`](docs/database-backup.md).

## Database boundaries

- `catalog`: countries, entities, nodes, corridors, projects, organizations, and vector geometry.
- `evidence`: sources, relationship assertions, lifecycle history, and provenance links.
- `observation`: monitoring runs and external imagery metadata.

Large imagery products stay in object storage. PostgreSQL records their URI, checksum, footprint, acquisition metadata, and processing state; it does not store image bytes.

The `infra-inventory-v0.1.0` seed is generated deterministically from the checked-in JSON inventory plus explicit normalization rules in `scripts/build_seed.py`. The seed produces 19 corridors, 73 normalized nodes, and ten project stubs. Reapplying it uses stable UUIDv5 identifiers and idempotent upserts.
