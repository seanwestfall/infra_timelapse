CREATE TABLE evidence.entity_relationships (
    relationship_id uuid PRIMARY KEY,
    subject_entity_id uuid NOT NULL
        REFERENCES catalog.entities(entity_id) ON DELETE CASCADE,
    relationship_type evidence.relationship_type NOT NULL,
    assertion_status evidence.relationship_assertion_status NOT NULL DEFAULT 'reported',
    status_as_of date NOT NULL,
    last_verified_on date,
    effective_from date,
    effective_to date,
    notes text,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT entity_relationships_verified_date_ck
        CHECK (
            assertion_status <> 'verified'
            OR last_verified_on IS NOT NULL
        ),
    CONSTRAINT entity_relationships_dates_ck
        CHECK (
            effective_from IS NULL
            OR effective_to IS NULL
            OR effective_from <= effective_to
        )
);

CREATE TABLE evidence.relationship_sources (
    relationship_id uuid NOT NULL
        REFERENCES evidence.entity_relationships(relationship_id)
        ON DELETE CASCADE,
    source_id uuid NOT NULL
        REFERENCES evidence.sources(source_id) ON DELETE RESTRICT,
    evidence_role evidence.evidence_role NOT NULL DEFAULT 'provenance',
    source_locator text,
    PRIMARY KEY (relationship_id, source_id)
);

CREATE TABLE evidence.entity_status_history (
    status_id uuid PRIMARY KEY,
    entity_id uuid NOT NULL
        REFERENCES catalog.entities(entity_id) ON DELETE CASCADE,
    lifecycle_status evidence.lifecycle_status NOT NULL,
    assertion_status evidence.relationship_assertion_status NOT NULL DEFAULT 'reported',
    status_as_of date NOT NULL,
    effective_from date,
    effective_to date,
    last_verified_on date,
    notes text,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT entity_status_history_verified_date_ck
        CHECK (
            assertion_status <> 'verified'
            OR last_verified_on IS NOT NULL
        ),
    CONSTRAINT entity_status_history_dates_ck
        CHECK (
            effective_from IS NULL
            OR effective_to IS NULL
            OR effective_from <= effective_to
        )
);

CREATE TABLE evidence.status_sources (
    status_id uuid NOT NULL
        REFERENCES evidence.entity_status_history(status_id) ON DELETE CASCADE,
    source_id uuid NOT NULL
        REFERENCES evidence.sources(source_id) ON DELETE RESTRICT,
    evidence_role evidence.evidence_role NOT NULL DEFAULT 'provenance',
    source_locator text,
    PRIMARY KEY (status_id, source_id)
);
