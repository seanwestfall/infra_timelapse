DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM evidence.sources
        WHERE url = 'https://github.com/seanwestfall/infra_timelapse/issues/1'
          AND is_substantive
    ) THEN
        RAISE EXCEPTION 'seed replay reset curated source substantiveness';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM catalog.entities
        WHERE code = 'n-lianyungang-port'
          AND record_status = 'deprecated'
    ) THEN
        RAISE EXCEPTION 'seed replay reset curated entity status';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM catalog.node_geometries AS geometries
        JOIN catalog.entities AS entities
          ON entities.entity_id = geometries.node_id
        WHERE entities.code = 'n-lianyungang-port'
          AND geometries.geometry_role = 'centroid'
          AND geometries.record_status = 'deprecated'
          AND NOT geometries.is_current
    ) THEN
        RAISE EXCEPTION 'seed replay reset curated node geometry state';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM catalog.corridor_geometries AS geometries
        JOIN catalog.entities AS entities
          ON entities.entity_id = geometries.corridor_id
        WHERE entities.code = 'cor-aadj'
          AND geometries.branch_code = 'main'
          AND geometries.record_status = 'deprecated'
          AND NOT geometries.is_current
    ) THEN
        RAISE EXCEPTION 'seed replay reset curated corridor geometry state';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM evidence.entity_relationships AS relationships
        JOIN catalog.entities AS entities
          ON entities.entity_id = relationships.subject_entity_id
        WHERE entities.code = 'cor-aadj'
          AND relationships.relationship_type = 'bri_linked'
          AND relationships.assertion_status = 'contested'
    ) THEN
        RAISE EXCEPTION 'seed replay reset curated relationship assertion';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM evidence.entity_status_history AS status_history
        JOIN catalog.entities AS entities
          ON entities.entity_id = status_history.entity_id
        WHERE entities.code = 'n-lianyungang-port'
          AND status_history.effective_to IS NULL
          AND status_history.lifecycle_status = 'suspended'
          AND status_history.assertion_status = 'contested'
    ) THEN
        RAISE EXCEPTION 'seed replay reset curated lifecycle assertion';
    END IF;
END;
$$;
