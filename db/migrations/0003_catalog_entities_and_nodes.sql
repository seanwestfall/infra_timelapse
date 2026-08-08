CREATE TABLE catalog.entities (
    entity_id uuid PRIMARY KEY,
    code text NOT NULL UNIQUE,
    entity_kind catalog.entity_kind NOT NULL,
    canonical_name text NOT NULL,
    record_status catalog.record_status NOT NULL DEFAULT 'draft',
    last_verified_on date,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT entities_code_format_ck
        CHECK (code ~ '^(n|cor|prj)-[a-z0-9]+(-[a-z0-9]+)*$'),
    CONSTRAINT entities_code_kind_ck
        CHECK (
            (entity_kind = 'node' AND code LIKE 'n-%')
            OR (entity_kind = 'corridor' AND code LIKE 'cor-%')
            OR (entity_kind = 'project' AND code LIKE 'prj-%')
        ),
    CONSTRAINT entities_name_nonempty_ck CHECK (btrim(canonical_name) <> ''),
    CONSTRAINT entities_verified_date_ck
        CHECK (record_status <> 'verified' OR last_verified_on IS NOT NULL)
);

CREATE TABLE catalog.seed_release_entities (
    seed_version text NOT NULL
        REFERENCES catalog.seed_releases(seed_version) ON DELETE RESTRICT,
    entity_id uuid NOT NULL
        REFERENCES catalog.entities(entity_id) ON DELETE RESTRICT,
    PRIMARY KEY (seed_version, entity_id)
);

CREATE TABLE catalog.nodes (
    entity_id uuid PRIMARY KEY
        REFERENCES catalog.entities(entity_id) ON DELETE CASCADE,
    node_type catalog.node_type NOT NULL,
    monitoring_tier catalog.monitoring_tier NOT NULL
);

CREATE TABLE catalog.node_aliases (
    node_id uuid NOT NULL
        REFERENCES catalog.nodes(entity_id) ON DELETE CASCADE,
    normalized_alias text NOT NULL,
    language_tag text NOT NULL DEFAULT 'und',
    alias text NOT NULL,
    PRIMARY KEY (node_id, normalized_alias, language_tag),
    CONSTRAINT node_aliases_alias_nonempty_ck CHECK (btrim(alias) <> ''),
    CONSTRAINT node_aliases_normalized_nonempty_ck
        CHECK (btrim(normalized_alias) <> ''),
    CONSTRAINT node_aliases_language_nonempty_ck
        CHECK (btrim(language_tag) <> '')
);

CREATE TABLE catalog.node_jurisdictions (
    node_id uuid NOT NULL
        REFERENCES catalog.nodes(entity_id) ON DELETE CASCADE,
    country_iso2 character(2) NOT NULL
        REFERENCES catalog.countries(iso2) ON DELETE RESTRICT,
    jurisdiction_role catalog.jurisdiction_role NOT NULL,
    PRIMARY KEY (node_id, country_iso2, jurisdiction_role)
);

CREATE TABLE catalog.node_geometries (
    geometry_id uuid PRIMARY KEY,
    node_id uuid NOT NULL
        REFERENCES catalog.nodes(entity_id) ON DELETE CASCADE,
    geometry_role catalog.geometry_role NOT NULL,
    geom geometry(Geometry, 4326) NOT NULL,
    source_id uuid NOT NULL
        REFERENCES evidence.sources(source_id) ON DELETE RESTRICT,
    derivation_kind catalog.geometry_derivation NOT NULL DEFAULT 'source',
    derived_from_geometry_id uuid
        REFERENCES catalog.node_geometries(geometry_id)
        DEFERRABLE INITIALLY DEFERRED,
    record_status catalog.record_status NOT NULL DEFAULT 'draft',
    is_current boolean NOT NULL DEFAULT true,
    verified_on date,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT node_geometries_not_empty_ck CHECK (NOT ST_IsEmpty(geom)),
    CONSTRAINT node_geometries_2d_ck CHECK (ST_NDims(geom) = 2),
    CONSTRAINT node_geometries_srid_ck CHECK (ST_SRID(geom) = 4326),
    CONSTRAINT node_geometries_role_type_ck
        CHECK (
            (geometry_role = 'centroid' AND GeometryType(geom) = 'POINT')
            OR (
                geometry_role IN ('boundary', 'satellite_aoi')
                AND GeometryType(geom) = 'MULTIPOLYGON'
            )
            OR (
                geometry_role = 'route_centerline'
                AND GeometryType(geom) = 'MULTILINESTRING'
            )
            OR (
                geometry_role = 'control_points'
                AND GeometryType(geom) = 'MULTIPOINT'
            )
        ),
    CONSTRAINT node_geometries_verified_ck
        CHECK (
            record_status <> 'verified'
            OR (verified_on IS NOT NULL AND ST_IsValid(geom))
        )
);

CREATE TABLE catalog.node_links (
    from_node_id uuid NOT NULL
        REFERENCES catalog.nodes(entity_id) ON DELETE CASCADE,
    to_node_id uuid NOT NULL
        REFERENCES catalog.nodes(entity_id) ON DELETE CASCADE,
    link_type catalog.node_link_type NOT NULL,
    PRIMARY KEY (from_node_id, to_node_id, link_type),
    CONSTRAINT node_links_not_self_ck CHECK (from_node_id <> to_node_id)
);
