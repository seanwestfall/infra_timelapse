# Database backup and recovery

Infra Timelapse has two backup domains: PostgreSQL/PostGIS metadata and imagery artifacts in external object storage. A usable recovery point requires both, plus a record of the common cutoff time.

## PostgreSQL/PostGIS metadata

Create a compressed logical backup with a PostgreSQL client compatible with the server major version:

```bash
pg_dump --dbname "$DATABASE_URL" --format=custom --file infra-timelapse.dump
pg_restore --list infra-timelapse.dump > infra-timelapse.dump.manifest
```

Encrypt the dump at rest, restrict access, and store it outside the database host. Record the server version, PostGIS version, Git commit, seed release, dump checksum, creation time, and the latest included monitoring-run timestamp alongside it. Do not commit dumps or credentials.

Restore into an empty PostgreSQL database where the supported PostGIS package is available:

```bash
pg_restore --dbname "$RESTORE_DATABASE_URL" --clean --if-exists --no-owner infra-timelapse.dump
DATABASE_URL="$RESTORE_DATABASE_URL" make db-validate
```

Use `--clean` only for a dedicated restore target whose existing contents may be replaced. Test restoration periodically and run the full validation suite before declaring the recovery point usable.

## Imagery and derived artifacts

PostgreSQL stores object URIs, checksums, footprints, provider identifiers, licenses, and processing state; it does not store the large files. Protect the object store independently with provider versioning or immutable copies in a separate failure domain.

For each database backup, export an object manifest containing the URI, version identifier when available, byte size, checksum, and retention class for every referenced artifact. Retain that manifest with the database dump. A recovery test must restore or sample-copy the corresponding object versions and verify them against `observation.imagery_assets.checksum_sha256`.

Coordinate backups by pausing ingestion or recording a precise cutoff before the database dump and object manifest are created. Objects newer than the cutoff may be replayed later; database rows must never be restored without their referenced object versions or an explicit record that those artifacts are unavailable.
