CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS catalog;
CREATE SCHEMA IF NOT EXISTS evidence;
CREATE SCHEMA IF NOT EXISTS observation;

COMMENT ON SCHEMA catalog IS
    'Normalized infrastructure entities, topology, projects, and vector geometry.';
COMMENT ON SCHEMA evidence IS
    'Sources, assertions, lifecycle history, verification, and provenance.';
COMMENT ON SCHEMA observation IS
    'Monitoring runs and external imagery metadata; large binary artifacts remain in object storage.';
