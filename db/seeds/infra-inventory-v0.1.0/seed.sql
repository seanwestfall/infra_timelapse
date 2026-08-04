\set ON_ERROR_STOP on
BEGIN;
\ir 001_countries_and_sources.sql
\ir 002_entities_and_subtypes.sql
\ir 003_node_details_and_geometries.sql
\ir 004_network_and_projects.sql
\ir 005_claims_and_status.sql
\ir 099_validate.sql
COMMIT;
