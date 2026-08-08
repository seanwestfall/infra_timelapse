CREATE TABLE catalog.corridors (
    entity_id uuid PRIMARY KEY
        REFERENCES catalog.entities(entity_id) ON DELETE CASCADE,
    corridor_type catalog.corridor_type NOT NULL,
    service_pattern catalog.service_pattern NOT NULL DEFAULT 'continuous'
);

CREATE TABLE catalog.corridor_geometries (
    geometry_id uuid PRIMARY KEY,
    corridor_id uuid NOT NULL
        REFERENCES catalog.corridors(entity_id) ON DELETE CASCADE,
    branch_code text NOT NULL DEFAULT 'main',
    geometry_role catalog.corridor_geometry_role NOT NULL DEFAULT 'schematic',
    route_geometry geometry(MultiLineString, 4326) NOT NULL,
    source_id uuid NOT NULL
        REFERENCES evidence.sources(source_id) ON DELETE RESTRICT,
    derivation_kind catalog.geometry_derivation NOT NULL DEFAULT 'normalized',
    derived_from_geometry_id uuid
        REFERENCES catalog.corridor_geometries(geometry_id)
        DEFERRABLE INITIALLY DEFERRED,
    record_status catalog.record_status NOT NULL DEFAULT 'draft',
    is_current boolean NOT NULL DEFAULT true,
    verified_on date,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT corridor_geometries_branch_nonempty_ck
        CHECK (btrim(branch_code) <> ''),
    CONSTRAINT corridor_geometries_not_empty_ck
        CHECK (NOT ST_IsEmpty(route_geometry)),
    CONSTRAINT corridor_geometries_2d_ck
        CHECK (ST_NDims(route_geometry) = 2),
    CONSTRAINT corridor_geometries_srid_ck
        CHECK (ST_SRID(route_geometry) = 4326),
    CONSTRAINT corridor_geometries_verified_ck
        CHECK (
            record_status <> 'verified'
            OR (verified_on IS NOT NULL AND ST_IsValid(route_geometry))
        )
);

CREATE TABLE catalog.corridor_nodes (
    corridor_id uuid NOT NULL
        REFERENCES catalog.corridors(entity_id) ON DELETE CASCADE,
    node_id uuid NOT NULL
        REFERENCES catalog.nodes(entity_id) ON DELETE CASCADE,
    branch_code text NOT NULL DEFAULT 'main',
    role catalog.corridor_node_role NOT NULL,
    membership_type catalog.corridor_membership_type NOT NULL,
    sequence_no integer,
    PRIMARY KEY (corridor_id, node_id, branch_code, role),
    CONSTRAINT corridor_nodes_branch_nonempty_ck
        CHECK (btrim(branch_code) <> ''),
    CONSTRAINT corridor_nodes_sequence_positive_ck
        CHECK (sequence_no IS NULL OR sequence_no > 0)
);

CREATE TABLE catalog.projects (
    entity_id uuid PRIMARY KEY
        REFERENCES catalog.entities(entity_id) ON DELETE CASCADE,
    project_type catalog.project_type NOT NULL
);

CREATE TABLE catalog.project_nodes (
    project_id uuid NOT NULL
        REFERENCES catalog.projects(entity_id) ON DELETE CASCADE,
    node_id uuid NOT NULL
        REFERENCES catalog.nodes(entity_id) ON DELETE CASCADE,
    role catalog.project_node_role NOT NULL,
    PRIMARY KEY (project_id, node_id, role)
);

CREATE TABLE catalog.organizations (
    organization_id uuid PRIMARY KEY,
    code text NOT NULL UNIQUE,
    canonical_name text NOT NULL,
    country_iso2 character(2)
        REFERENCES catalog.countries(iso2) ON DELETE RESTRICT,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT organizations_code_format_ck
        CHECK (code ~ '^org-[a-z0-9]+(-[a-z0-9]+)*$'),
    CONSTRAINT organizations_name_nonempty_ck
        CHECK (btrim(canonical_name) <> '')
);

CREATE TABLE catalog.project_parties (
    party_id uuid PRIMARY KEY,
    project_id uuid NOT NULL
        REFERENCES catalog.projects(entity_id) ON DELETE CASCADE,
    organization_id uuid NOT NULL
        REFERENCES catalog.organizations(organization_id) ON DELETE RESTRICT,
    party_role catalog.party_role NOT NULL,
    ownership_percentage numeric(5, 2),
    effective_from date,
    effective_to date,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT project_parties_percentage_ck
        CHECK (
            ownership_percentage IS NULL
            OR ownership_percentage BETWEEN 0 AND 100
        ),
    CONSTRAINT project_parties_dates_ck
        CHECK (
            effective_from IS NULL
            OR effective_to IS NULL
            OR effective_from <= effective_to
        )
);
