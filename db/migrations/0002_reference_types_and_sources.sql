CREATE TYPE catalog.entity_kind AS ENUM (
    'node',
    'corridor',
    'project'
);

CREATE TYPE catalog.record_status AS ENUM (
    'draft',
    'verified',
    'deprecated'
);

CREATE TYPE catalog.node_type AS ENUM (
    'port_system',
    'port_complex',
    'seaport',
    'container_terminal',
    'bulk_terminal',
    'fishing_port',
    'dry_port',
    'inland_port',
    'rail_hub',
    'border_gateway',
    'military_logistics_facility',
    'naval_base',
    'canal',
    'strait',
    'route_overlay'
);

CREATE TYPE catalog.monitoring_tier AS ENUM (
    'priority',
    'expanded',
    'watchlist',
    'overlay'
);

CREATE TYPE catalog.jurisdiction_role AS ENUM (
    'primary',
    'bordering',
    'shoreline'
);

CREATE TYPE catalog.geometry_role AS ENUM (
    'centroid',
    'boundary',
    'satellite_aoi',
    'route_centerline',
    'control_points'
);

CREATE TYPE catalog.geometry_derivation AS ENUM (
    'source',
    'normalized',
    'simplified',
    'manual'
);

CREATE TYPE catalog.node_link_type AS ENUM (
    'contains',
    'paired_with',
    'same_harbor'
);

CREATE TYPE catalog.corridor_type AS ENUM (
    'land',
    'maritime',
    'multimodal'
);

CREATE TYPE catalog.service_pattern AS ENUM (
    'continuous',
    'seasonal',
    'mixed',
    'proposed'
);

CREATE TYPE catalog.corridor_geometry_role AS ENUM (
    'primary',
    'alternative',
    'schematic'
);

CREATE TYPE catalog.corridor_membership_type AS ENUM (
    'official_route',
    'linked',
    'adjacent',
    'overlay'
);

CREATE TYPE catalog.corridor_node_role AS ENUM (
    'origin',
    'terminus',
    'anchor',
    'gateway',
    'border_crossing',
    'rail_hub',
    'transfer_point',
    'transshipment_hub',
    'maritime_outlet',
    'distribution_hub',
    'intermediate',
    'adjacent',
    'overlay',
    'security_support'
);

CREATE TYPE catalog.project_type AS ENUM (
    'railway',
    'port_development',
    'port_expansion',
    'logistics',
    'feasibility_study',
    'rehabilitation',
    'mixed_infrastructure'
);

CREATE TYPE catalog.project_node_role AS ENUM (
    'anchor',
    'site',
    'origin',
    'terminus',
    'affected_asset'
);

CREATE TYPE catalog.party_role AS ENUM (
    'financier',
    'owner',
    'operator',
    'epc_contractor',
    'concessionaire'
);

CREATE TYPE evidence.source_kind AS ENUM (
    'project_inventory',
    'official',
    'dataset',
    'coordinate',
    'report',
    'other'
);

CREATE TYPE evidence.evidence_role AS ENUM (
    'provenance',
    'substantive',
    'coordinate'
);

CREATE TYPE evidence.relationship_type AS ENUM (
    'official_bri_designation',
    'bri_linked',
    'prc_financed',
    'prc_owned',
    'prc_operated',
    'prc_epc_contractor',
    'strategically_adjacent',
    'prc_security_presence'
);

CREATE TYPE evidence.relationship_assertion_status AS ENUM (
    'reported',
    'verified',
    'contested',
    'superseded'
);

CREATE TYPE evidence.lifecycle_status AS ENUM (
    'unknown',
    'concept',
    'pledged',
    'proposed',
    'feasibility',
    'planned',
    'under_construction',
    'delayed',
    'partially_operational',
    'operational',
    'expanding',
    'dormant',
    'suspended',
    'cancelled',
    'decommissioned'
);

CREATE TYPE observation.run_status AS ENUM (
    'pending',
    'running',
    'succeeded',
    'failed',
    'cancelled'
);

CREATE TYPE observation.processing_state AS ENUM (
    'discovered',
    'ingested',
    'processed',
    'failed'
);

CREATE TABLE catalog.countries (
    iso2 character(2) PRIMARY KEY,
    iso3 character(3) NOT NULL UNIQUE,
    name text NOT NULL,
    CONSTRAINT countries_iso2_uppercase_ck
        CHECK (btrim(iso2) ~ '^[A-Z]{2}$'),
    CONSTRAINT countries_iso3_uppercase_ck
        CHECK (btrim(iso3) ~ '^[A-Z]{3}$'),
    CONSTRAINT countries_name_nonempty_ck
        CHECK (btrim(name) <> '')
);

CREATE TABLE evidence.sources (
    source_id uuid PRIMARY KEY,
    url text NOT NULL UNIQUE,
    title text NOT NULL,
    publisher text NOT NULL,
    source_kind evidence.source_kind NOT NULL,
    is_substantive boolean NOT NULL DEFAULT false,
    accessed_on date NOT NULL,
    license_code text,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT sources_url_nonempty_ck CHECK (btrim(url) <> ''),
    CONSTRAINT sources_title_nonempty_ck CHECK (btrim(title) <> ''),
    CONSTRAINT sources_publisher_nonempty_ck CHECK (btrim(publisher) <> '')
);

CREATE TABLE catalog.seed_releases (
    seed_version text PRIMARY KEY,
    source_uri text NOT NULL,
    source_updated_at timestamp with time zone NOT NULL,
    source_sha256 character(64) NOT NULL,
    applied_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT seed_releases_version_nonempty_ck
        CHECK (btrim(seed_version) <> ''),
    CONSTRAINT seed_releases_sha256_ck
        CHECK (btrim(source_sha256) ~ '^[0-9a-f]{64}$')
);
