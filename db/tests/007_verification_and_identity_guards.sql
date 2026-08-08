BEGIN;

INSERT INTO evidence.sources (
    source_id,
    url,
    title,
    publisher,
    source_kind,
    is_substantive,
    accessed_on
) VALUES
    (
        '11111111-1111-4111-8111-111111111111',
        'https://example.invalid/verification-node',
        'Verification node fixture',
        'Infra Timelapse tests',
        'other',
        true,
        DATE '2026-08-08'
    ),
    (
        '22222222-2222-4222-8222-222222222222',
        'https://example.invalid/verification-relationship',
        'Verification relationship fixture',
        'Infra Timelapse tests',
        'other',
        true,
        DATE '2026-08-08'
    );

UPDATE catalog.node_geometries
SET record_status = 'verified',
    is_current = true,
    verified_on = DATE '2026-08-08'
WHERE node_id = (
    SELECT entity_id
    FROM catalog.entities
    WHERE code = 'n-lianyungang-port'
)
  AND geometry_role = 'centroid';

UPDATE evidence.entity_status_history
SET lifecycle_status = 'operational',
    assertion_status = 'verified',
    last_verified_on = DATE '2026-08-08'
WHERE entity_id = (
    SELECT entity_id
    FROM catalog.entities
    WHERE code = 'n-lianyungang-port'
)
  AND effective_to IS NULL;

UPDATE evidence.status_sources
SET source_id = '11111111-1111-4111-8111-111111111111',
    evidence_role = 'substantive'
WHERE status_id = (
    SELECT status_id
    FROM evidence.entity_status_history
    WHERE entity_id = (
        SELECT entity_id
        FROM catalog.entities
        WHERE code = 'n-lianyungang-port'
    )
      AND effective_to IS NULL
);

UPDATE catalog.entities
SET record_status = 'verified',
    last_verified_on = DATE '2026-08-08'
WHERE code = 'n-lianyungang-port';

UPDATE evidence.relationship_sources
SET source_id = '22222222-2222-4222-8222-222222222222',
    evidence_role = 'substantive'
WHERE relationship_id = (
    SELECT relationship_id
    FROM evidence.entity_relationships
    WHERE subject_entity_id = (
        SELECT entity_id
        FROM catalog.entities
        WHERE code = 'cor-aadj'
    )
      AND relationship_type = 'bri_linked'
);

UPDATE evidence.entity_relationships
SET assertion_status = 'verified',
    last_verified_on = DATE '2026-08-08'
WHERE subject_entity_id = (
    SELECT entity_id
    FROM catalog.entities
    WHERE code = 'cor-aadj'
)
  AND relationship_type = 'bri_linked';

SET CONSTRAINTS ALL IMMEDIATE;

DO $$
DECLARE
    rejected boolean := false;
BEGIN
    BEGIN
        UPDATE catalog.entities
        SET code = 'n-lianyungang-port-renamed'
        WHERE code = 'n-lianyungang-port';
    EXCEPTION WHEN raise_exception THEN
        rejected := true;
    END;

    IF NOT rejected THEN
        RAISE EXCEPTION 'entity code mutation was accepted';
    END IF;
END;
$$;

DO $$
DECLARE
    rejected boolean := false;
BEGIN
    BEGIN
        UPDATE catalog.entities
        SET code = 'cor-lianyungang-port',
            entity_kind = 'corridor'
        WHERE code = 'n-lianyungang-port';
    EXCEPTION WHEN raise_exception THEN
        rejected := true;
    END;

    IF NOT rejected THEN
        RAISE EXCEPTION 'entity kind mutation was accepted';
    END IF;
END;
$$;

DO $$
DECLARE
    rejected boolean := false;
BEGIN
    BEGIN
        UPDATE catalog.entities
        SET record_status = 'verified',
            last_verified_on = DATE '2026-08-08'
        WHERE code IN ('cor-pbb', 'prj-pbb-rail-buildout');
    EXCEPTION WHEN check_violation THEN
        rejected := true;
    END;

    IF NOT rejected THEN
        RAISE EXCEPTION 'corridor/project verification was accepted without gates';
    END IF;
END;
$$;

DO $$
DECLARE
    rejected boolean := false;
BEGIN
    BEGIN
        UPDATE catalog.node_jurisdictions
        SET node_id = (
            SELECT entity_id
            FROM catalog.entities
            WHERE code = 'n-piraeus-port'
        )
        WHERE node_id = (
            SELECT entity_id
            FROM catalog.entities
            WHERE code = 'n-lianyungang-port'
        );
    EXCEPTION WHEN raise_exception THEN
        rejected := true;
    END;

    IF NOT rejected THEN
        RAISE EXCEPTION 'jurisdiction reassignment bypassed the old-node gate';
    END IF;
END;
$$;

DO $$
DECLARE
    rejected boolean := false;
BEGIN
    BEGIN
        UPDATE catalog.node_geometries
        SET node_id = (
                SELECT entity_id
                FROM catalog.entities
                WHERE code = 'n-piraeus-port'
            ),
            is_current = false
        WHERE node_id = (
            SELECT entity_id
            FROM catalog.entities
            WHERE code = 'n-lianyungang-port'
        )
          AND geometry_role = 'centroid';
    EXCEPTION WHEN raise_exception THEN
        rejected := true;
    END;

    IF NOT rejected THEN
        RAISE EXCEPTION 'geometry reassignment bypassed the old-node gate';
    END IF;
END;
$$;

DO $$
DECLARE
    rejected boolean := false;
BEGIN
    BEGIN
        UPDATE evidence.entity_status_history
        SET entity_id = (
                SELECT entity_id
                FROM catalog.entities
                WHERE code = 'n-piraeus-port'
            ),
            effective_to = DATE '2026-08-08'
        WHERE entity_id = (
            SELECT entity_id
            FROM catalog.entities
            WHERE code = 'n-lianyungang-port'
        )
          AND effective_to IS NULL;
    EXCEPTION WHEN raise_exception THEN
        rejected := true;
    END;

    IF NOT rejected THEN
        RAISE EXCEPTION 'status reassignment bypassed the old-node gate';
    END IF;
END;
$$;

DO $$
DECLARE
    rejected boolean := false;
BEGIN
    BEGIN
        UPDATE evidence.status_sources
        SET status_id = (
            SELECT status_id
            FROM evidence.entity_status_history
            WHERE entity_id = (
                SELECT entity_id
                FROM catalog.entities
                WHERE code = 'n-piraeus-port'
            )
              AND effective_to IS NULL
        )
        WHERE source_id = '11111111-1111-4111-8111-111111111111';
    EXCEPTION WHEN raise_exception THEN
        rejected := true;
    END;

    IF NOT rejected THEN
        RAISE EXCEPTION 'status-source reassignment bypassed the old-node gate';
    END IF;
END;
$$;

DO $$
DECLARE
    rejected boolean := false;
BEGIN
    BEGIN
        UPDATE evidence.relationship_sources
        SET relationship_id = (
            SELECT relationship_id
            FROM evidence.entity_relationships
            WHERE subject_entity_id = (
                SELECT entity_id
                FROM catalog.entities
                WHERE code = 'cor-pbb'
            )
              AND relationship_type = 'bri_linked'
        )
        WHERE source_id = '22222222-2222-4222-8222-222222222222';
    EXCEPTION WHEN raise_exception THEN
        rejected := true;
    END;

    IF NOT rejected THEN
        RAISE EXCEPTION 'relationship-source reassignment bypassed the old-owner gate';
    END IF;
END;
$$;

DO $$
DECLARE
    rejected boolean := false;
BEGIN
    BEGIN
        UPDATE evidence.sources
        SET is_substantive = false
        WHERE source_id = '11111111-1111-4111-8111-111111111111';
    EXCEPTION WHEN raise_exception THEN
        rejected := true;
    END;

    IF NOT rejected THEN
        RAISE EXCEPTION 'source demotion bypassed verified-node revalidation';
    END IF;
END;
$$;

DO $$
DECLARE
    rejected boolean := false;
BEGIN
    BEGIN
        UPDATE evidence.sources
        SET is_substantive = false
        WHERE source_id = '22222222-2222-4222-8222-222222222222';
    EXCEPTION WHEN raise_exception THEN
        rejected := true;
    END;

    IF NOT rejected THEN
        RAISE EXCEPTION 'source demotion bypassed verified-relationship revalidation';
    END IF;
END;
$$;

ROLLBACK;
