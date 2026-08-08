DO $$
DECLARE
    affected_rows integer;
BEGIN
    UPDATE evidence.sources
    SET is_substantive = true
    WHERE url = 'https://github.com/seanwestfall/infra_timelapse/issues/1';
    GET DIAGNOSTICS affected_rows = ROW_COUNT;
    IF affected_rows <> 1 THEN
        RAISE EXCEPTION 'expected to curate one source, updated %', affected_rows;
    END IF;

    UPDATE catalog.entities
    SET record_status = 'deprecated'
    WHERE code = 'n-lianyungang-port';
    GET DIAGNOSTICS affected_rows = ROW_COUNT;
    IF affected_rows <> 1 THEN
        RAISE EXCEPTION 'expected to curate one entity, updated %', affected_rows;
    END IF;

    UPDATE catalog.node_geometries
    SET record_status = 'deprecated',
        is_current = false
    WHERE node_id = (
        SELECT entity_id
        FROM catalog.entities
        WHERE code = 'n-lianyungang-port'
    )
      AND geometry_role = 'centroid';
    GET DIAGNOSTICS affected_rows = ROW_COUNT;
    IF affected_rows <> 1 THEN
        RAISE EXCEPTION 'expected to curate one node geometry, updated %', affected_rows;
    END IF;

    UPDATE catalog.corridor_geometries
    SET record_status = 'deprecated',
        is_current = false
    WHERE corridor_id = (
        SELECT entity_id
        FROM catalog.entities
        WHERE code = 'cor-aadj'
    )
      AND branch_code = 'main';
    GET DIAGNOSTICS affected_rows = ROW_COUNT;
    IF affected_rows <> 1 THEN
        RAISE EXCEPTION 'expected to curate one corridor geometry, updated %', affected_rows;
    END IF;

    UPDATE evidence.entity_relationships
    SET assertion_status = 'contested'
    WHERE subject_entity_id = (
        SELECT entity_id
        FROM catalog.entities
        WHERE code = 'cor-aadj'
    )
      AND relationship_type = 'bri_linked';
    GET DIAGNOSTICS affected_rows = ROW_COUNT;
    IF affected_rows <> 1 THEN
        RAISE EXCEPTION 'expected to curate one relationship, updated %', affected_rows;
    END IF;

    UPDATE evidence.entity_status_history
    SET lifecycle_status = 'suspended',
        assertion_status = 'contested'
    WHERE entity_id = (
        SELECT entity_id
        FROM catalog.entities
        WHERE code = 'n-lianyungang-port'
    )
      AND effective_to IS NULL;
    GET DIAGNOSTICS affected_rows = ROW_COUNT;
    IF affected_rows <> 1 THEN
        RAISE EXCEPTION 'expected to curate one lifecycle row, updated %', affected_rows;
    END IF;
END;
$$;
