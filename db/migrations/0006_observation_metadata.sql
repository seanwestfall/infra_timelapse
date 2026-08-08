CREATE TABLE observation.monitoring_runs (
    monitoring_run_id uuid PRIMARY KEY,
    run_status observation.run_status NOT NULL DEFAULT 'pending',
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    code_version text,
    seed_version text
        REFERENCES catalog.seed_releases(seed_version) ON DELETE RESTRICT,
    configuration jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT monitoring_runs_dates_ck
        CHECK (
            started_at IS NULL
            OR finished_at IS NULL
            OR started_at <= finished_at
        )
);

CREATE TABLE observation.imagery_assets (
    imagery_asset_id uuid PRIMARY KEY,
    monitoring_run_id uuid
        REFERENCES observation.monitoring_runs(monitoring_run_id)
        ON DELETE SET NULL,
    provider text NOT NULL,
    provider_asset_id text NOT NULL,
    captured_at timestamp with time zone,
    published_at timestamp with time zone,
    storage_uri text,
    media_type text NOT NULL,
    checksum_sha256 character(64),
    footprint geometry(MultiPolygon, 4326),
    cloud_cover_pct numeric(5, 2),
    ground_sample_distance_m numeric(12, 4),
    license_code text,
    processing_level text,
    source_url text,
    processing_state observation.processing_state NOT NULL DEFAULT 'discovered',
    record_status catalog.record_status NOT NULL DEFAULT 'draft',
    ingested_at timestamp with time zone NOT NULL DEFAULT now(),
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_asset_id),
    CONSTRAINT imagery_assets_provider_nonempty_ck
        CHECK (btrim(provider) <> ''),
    CONSTRAINT imagery_assets_provider_id_nonempty_ck
        CHECK (btrim(provider_asset_id) <> ''),
    CONSTRAINT imagery_assets_media_type_nonempty_ck
        CHECK (btrim(media_type) <> ''),
    CONSTRAINT imagery_assets_checksum_ck
        CHECK (
            checksum_sha256 IS NULL
            OR btrim(checksum_sha256) ~ '^[0-9a-f]{64}$'
        ),
    CONSTRAINT imagery_assets_cloud_cover_ck
        CHECK (
            cloud_cover_pct IS NULL
            OR cloud_cover_pct BETWEEN 0 AND 100
        ),
    CONSTRAINT imagery_assets_gsd_ck
        CHECK (
            ground_sample_distance_m IS NULL
            OR ground_sample_distance_m > 0
        ),
    CONSTRAINT imagery_assets_footprint_ck
        CHECK (
            footprint IS NULL
            OR (
                NOT ST_IsEmpty(footprint)
                AND ST_NDims(footprint) = 2
                AND ST_SRID(footprint) = 4326
            )
        ),
    CONSTRAINT imagery_assets_verified_ck
        CHECK (
            record_status <> 'verified'
            OR (
                captured_at IS NOT NULL
                AND storage_uri IS NOT NULL
                AND checksum_sha256 IS NOT NULL
                AND footprint IS NOT NULL
                AND ST_IsValid(footprint)
            )
        )
);

CREATE TABLE observation.imagery_asset_nodes (
    imagery_asset_id uuid NOT NULL
        REFERENCES observation.imagery_assets(imagery_asset_id)
        ON DELETE CASCADE,
    node_id uuid NOT NULL
        REFERENCES catalog.nodes(entity_id) ON DELETE CASCADE,
    PRIMARY KEY (imagery_asset_id, node_id)
);
