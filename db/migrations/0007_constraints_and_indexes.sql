CREATE FUNCTION catalog.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER entities_set_updated_at
BEFORE UPDATE ON catalog.entities
FOR EACH ROW EXECUTE FUNCTION catalog.set_updated_at();

CREATE TRIGGER organizations_set_updated_at
BEFORE UPDATE ON catalog.organizations
FOR EACH ROW EXECUTE FUNCTION catalog.set_updated_at();

CREATE TRIGGER entity_relationships_set_updated_at
BEFORE UPDATE ON evidence.entity_relationships
FOR EACH ROW EXECUTE FUNCTION catalog.set_updated_at();

CREATE FUNCTION catalog.enforce_subtype_entity_kind()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    actual_kind catalog.entity_kind;
    expected_kind catalog.entity_kind;
BEGIN
    expected_kind := CASE TG_TABLE_NAME
        WHEN 'nodes' THEN 'node'::catalog.entity_kind
        WHEN 'corridors' THEN 'corridor'::catalog.entity_kind
        WHEN 'projects' THEN 'project'::catalog.entity_kind
        ELSE NULL
    END;

    SELECT entity_kind
    INTO actual_kind
    FROM catalog.entities
    WHERE entity_id = NEW.entity_id;

    IF actual_kind IS DISTINCT FROM expected_kind THEN
        RAISE EXCEPTION
            'entity % has kind %, but %.% requires %',
            NEW.entity_id,
            actual_kind,
            TG_TABLE_SCHEMA,
            TG_TABLE_NAME,
            expected_kind;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER nodes_entity_kind
BEFORE INSERT OR UPDATE OF entity_id ON catalog.nodes
FOR EACH ROW EXECUTE FUNCTION catalog.enforce_subtype_entity_kind();

CREATE TRIGGER corridors_entity_kind
BEFORE INSERT OR UPDATE OF entity_id ON catalog.corridors
FOR EACH ROW EXECUTE FUNCTION catalog.enforce_subtype_entity_kind();

CREATE TRIGGER projects_entity_kind
BEFORE INSERT OR UPDATE OF entity_id ON catalog.projects
FOR EACH ROW EXECUTE FUNCTION catalog.enforce_subtype_entity_kind();

CREATE FUNCTION catalog.assert_verified_node(p_node_id uuid)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    node_record_status catalog.record_status;
    verified_node_type catalog.node_type;
BEGIN
    SELECT entities.record_status, nodes.node_type
    INTO node_record_status, verified_node_type
    FROM catalog.nodes AS nodes
    JOIN catalog.entities AS entities
      ON entities.entity_id = nodes.entity_id
    WHERE nodes.entity_id = p_node_id;

    IF NOT FOUND OR node_record_status <> 'verified' THEN
        RETURN;
    END IF;

    IF verified_node_type <> 'route_overlay'
       AND NOT EXISTS (
           SELECT 1
           FROM catalog.node_jurisdictions
           WHERE node_id = p_node_id
       ) THEN
        RAISE EXCEPTION
            'verified node % requires at least one jurisdiction',
            p_node_id;
    END IF;

    IF verified_node_type IN ('canal', 'strait', 'route_overlay') THEN
        IF NOT EXISTS (
            SELECT 1
            FROM catalog.node_geometries
            WHERE node_id = p_node_id
              AND is_current
              AND record_status = 'verified'
        ) THEN
            RAISE EXCEPTION
                'verified route or chokepoint node % requires a current verified geometry',
                p_node_id;
        END IF;
    ELSE
        IF NOT EXISTS (
            SELECT 1
            FROM catalog.node_geometries
            WHERE node_id = p_node_id
              AND geometry_role IN ('centroid', 'boundary')
              AND is_current
              AND record_status = 'verified'
        ) THEN
            RAISE EXCEPTION
                'verified physical node % requires a current verified centroid or boundary',
                p_node_id;
        END IF;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM evidence.entity_status_history AS status_history
        JOIN evidence.status_sources AS status_sources
          ON status_sources.status_id = status_history.status_id
        JOIN evidence.sources AS sources
          ON sources.source_id = status_sources.source_id
        WHERE status_history.entity_id = p_node_id
          AND status_history.effective_to IS NULL
          AND status_history.assertion_status = 'verified'
          AND status_history.last_verified_on IS NOT NULL
          AND status_sources.evidence_role = 'substantive'
          AND sources.is_substantive
    ) THEN
        RAISE EXCEPTION
            'verified node % requires a verified current status with substantive evidence',
            p_node_id;
    END IF;
END;
$$;

CREATE FUNCTION catalog.check_verified_entity_node_trigger()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.entity_kind = 'node' THEN
        PERFORM catalog.assert_verified_node(NEW.entity_id);
    END IF;
    RETURN NULL;
END;
$$;

CREATE FUNCTION catalog.check_verified_node_dependency_trigger()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    affected_node_id uuid;
BEGIN
    IF TG_OP = 'DELETE' THEN
        affected_node_id := (to_jsonb(OLD) ->> 'node_id')::uuid;
    ELSE
        affected_node_id := (to_jsonb(NEW) ->> 'node_id')::uuid;
    END IF;

    PERFORM catalog.assert_verified_node(affected_node_id);
    RETURN NULL;
END;
$$;

CREATE FUNCTION catalog.check_verified_status_trigger()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    affected_entity_id uuid;
BEGIN
    IF TG_OP = 'DELETE' THEN
        affected_entity_id := OLD.entity_id;
    ELSE
        affected_entity_id := NEW.entity_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM catalog.nodes
        WHERE entity_id = affected_entity_id
    ) THEN
        PERFORM catalog.assert_verified_node(affected_entity_id);
    END IF;
    RETURN NULL;
END;
$$;

CREATE FUNCTION catalog.check_verified_status_source_trigger()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    affected_status_id uuid;
    affected_entity_id uuid;
BEGIN
    IF TG_OP = 'DELETE' THEN
        affected_status_id := OLD.status_id;
    ELSE
        affected_status_id := NEW.status_id;
    END IF;

    SELECT entity_id
    INTO affected_entity_id
    FROM evidence.entity_status_history
    WHERE status_id = affected_status_id;

    IF affected_entity_id IS NOT NULL
       AND EXISTS (
           SELECT 1 FROM catalog.nodes WHERE entity_id = affected_entity_id
       ) THEN
        PERFORM catalog.assert_verified_node(affected_entity_id);
    END IF;
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER verified_node_entity_ck
AFTER INSERT OR UPDATE ON catalog.entities
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION catalog.check_verified_entity_node_trigger();

CREATE CONSTRAINT TRIGGER verified_node_jurisdiction_ck
AFTER INSERT OR UPDATE OR DELETE ON catalog.node_jurisdictions
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION catalog.check_verified_node_dependency_trigger();

CREATE CONSTRAINT TRIGGER verified_node_geometry_ck
AFTER INSERT OR UPDATE OR DELETE ON catalog.node_geometries
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION catalog.check_verified_node_dependency_trigger();

CREATE CONSTRAINT TRIGGER verified_node_status_ck
AFTER INSERT OR UPDATE OR DELETE ON evidence.entity_status_history
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION catalog.check_verified_status_trigger();

CREATE CONSTRAINT TRIGGER verified_node_status_source_ck
AFTER INSERT OR UPDATE OR DELETE ON evidence.status_sources
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION catalog.check_verified_status_source_trigger();

CREATE FUNCTION evidence.assert_verified_relationship(p_relationship_id uuid)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    current_assertion_status evidence.relationship_assertion_status;
BEGIN
    SELECT assertion_status
    INTO current_assertion_status
    FROM evidence.entity_relationships
    WHERE relationship_id = p_relationship_id;

    IF NOT FOUND OR current_assertion_status <> 'verified' THEN
        RETURN;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM evidence.relationship_sources AS relationship_sources
        JOIN evidence.sources AS sources
          ON sources.source_id = relationship_sources.source_id
        WHERE relationship_sources.relationship_id = p_relationship_id
          AND relationship_sources.evidence_role = 'substantive'
          AND sources.is_substantive
    ) THEN
        RAISE EXCEPTION
            'verified relationship % requires substantive evidence',
            p_relationship_id;
    END IF;
END;
$$;

CREATE FUNCTION evidence.check_verified_relationship_trigger()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    affected_relationship_id uuid;
BEGIN
    IF TG_OP = 'DELETE' THEN
        affected_relationship_id := OLD.relationship_id;
    ELSE
        affected_relationship_id := NEW.relationship_id;
    END IF;

    PERFORM evidence.assert_verified_relationship(affected_relationship_id);
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER verified_relationship_ck
AFTER INSERT OR UPDATE ON evidence.entity_relationships
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION evidence.check_verified_relationship_trigger();

CREATE CONSTRAINT TRIGGER verified_relationship_source_ck
AFTER INSERT OR UPDATE OR DELETE ON evidence.relationship_sources
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION evidence.check_verified_relationship_trigger();

CREATE UNIQUE INDEX node_geometries_current_role_uq
    ON catalog.node_geometries (node_id, geometry_role)
    WHERE is_current;

CREATE UNIQUE INDEX corridor_geometries_current_role_uq
    ON catalog.corridor_geometries (
        corridor_id,
        branch_code,
        geometry_role
    )
    WHERE is_current;

CREATE UNIQUE INDEX corridor_nodes_sequence_uq
    ON catalog.corridor_nodes (corridor_id, branch_code, sequence_no)
    WHERE sequence_no IS NOT NULL;

CREATE UNIQUE INDEX entity_status_history_current_uq
    ON evidence.entity_status_history (entity_id)
    WHERE effective_to IS NULL AND assertion_status <> 'superseded';

CREATE UNIQUE INDEX project_parties_current_uq
    ON catalog.project_parties (project_id, organization_id, party_role)
    WHERE effective_to IS NULL;

CREATE INDEX seed_release_entities_entity_idx
    ON catalog.seed_release_entities (entity_id);
CREATE INDEX node_aliases_normalized_idx
    ON catalog.node_aliases (normalized_alias);
CREATE INDEX node_jurisdictions_country_idx
    ON catalog.node_jurisdictions (country_iso2);
CREATE INDEX node_geometries_node_idx
    ON catalog.node_geometries (node_id, geometry_role, is_current);
CREATE INDEX node_links_to_idx
    ON catalog.node_links (to_node_id);
CREATE INDEX corridor_nodes_node_idx
    ON catalog.corridor_nodes (node_id);
CREATE INDEX project_nodes_node_idx
    ON catalog.project_nodes (node_id);
CREATE INDEX project_parties_organization_idx
    ON catalog.project_parties (organization_id);
CREATE INDEX entity_relationships_subject_idx
    ON evidence.entity_relationships (subject_entity_id, relationship_type);
CREATE INDEX relationship_sources_source_idx
    ON evidence.relationship_sources (source_id);
CREATE INDEX entity_status_history_entity_idx
    ON evidence.entity_status_history (entity_id, status_as_of DESC);
CREATE INDEX status_sources_source_idx
    ON evidence.status_sources (source_id);
CREATE INDEX imagery_assets_captured_idx
    ON observation.imagery_assets (captured_at DESC);
CREATE INDEX imagery_asset_nodes_node_idx
    ON observation.imagery_asset_nodes (node_id);

CREATE INDEX node_geometries_centroid_gix
    ON catalog.node_geometries USING gist (geom)
    WHERE is_current AND geometry_role = 'centroid';

CREATE INDEX node_geometries_area_gix
    ON catalog.node_geometries USING gist (geom)
    WHERE is_current AND geometry_role IN ('boundary', 'satellite_aoi');

CREATE INDEX node_geometries_route_gix
    ON catalog.node_geometries USING gist (geom)
    WHERE is_current AND geometry_role IN ('route_centerline', 'control_points');

CREATE INDEX node_geometries_centroid_geography_gix
    ON catalog.node_geometries USING gist ((geom::geography))
    WHERE is_current AND geometry_role = 'centroid';

CREATE INDEX corridor_geometries_route_gix
    ON catalog.corridor_geometries USING gist (route_geometry)
    WHERE is_current;

CREATE INDEX imagery_assets_footprint_gix
    ON observation.imagery_assets USING gist (footprint)
    WHERE footprint IS NOT NULL;
