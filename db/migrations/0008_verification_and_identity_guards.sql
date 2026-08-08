CREATE FUNCTION catalog.enforce_immutable_entity_identity()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.code IS DISTINCT FROM OLD.code
       OR NEW.entity_kind IS DISTINCT FROM OLD.entity_kind THEN
        RAISE EXCEPTION
            'entity identity is immutable (entity_id %, code %, kind %)',
            OLD.entity_id,
            OLD.code,
            OLD.entity_kind;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER entities_immutable_identity
BEFORE UPDATE OF code, entity_kind ON catalog.entities
FOR EACH ROW EXECUTE FUNCTION catalog.enforce_immutable_entity_identity();

ALTER TABLE catalog.entities
ADD CONSTRAINT entities_verified_kind_ck
CHECK (record_status <> 'verified' OR entity_kind = 'node');

CREATE OR REPLACE FUNCTION catalog.check_verified_node_dependency_trigger()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    old_node_id uuid;
    new_node_id uuid;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        old_node_id := (to_jsonb(OLD) ->> 'node_id')::uuid;
        PERFORM catalog.assert_verified_node(old_node_id);
    END IF;

    IF TG_OP <> 'DELETE' THEN
        new_node_id := (to_jsonb(NEW) ->> 'node_id')::uuid;
        IF new_node_id IS DISTINCT FROM old_node_id THEN
            PERFORM catalog.assert_verified_node(new_node_id);
        END IF;
    END IF;

    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION catalog.check_verified_status_trigger()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    old_entity_id uuid;
    new_entity_id uuid;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        old_entity_id := OLD.entity_id;
        PERFORM catalog.assert_verified_node(old_entity_id);
    END IF;

    IF TG_OP <> 'DELETE' THEN
        new_entity_id := NEW.entity_id;
        IF new_entity_id IS DISTINCT FROM old_entity_id THEN
            PERFORM catalog.assert_verified_node(new_entity_id);
        END IF;
    END IF;

    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION catalog.check_verified_status_source_trigger()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    old_entity_id uuid;
    new_entity_id uuid;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        SELECT entity_id
        INTO old_entity_id
        FROM evidence.entity_status_history
        WHERE status_id = OLD.status_id;

        IF old_entity_id IS NOT NULL THEN
            PERFORM catalog.assert_verified_node(old_entity_id);
        END IF;
    END IF;

    IF TG_OP <> 'DELETE' THEN
        SELECT entity_id
        INTO new_entity_id
        FROM evidence.entity_status_history
        WHERE status_id = NEW.status_id;

        IF new_entity_id IS NOT NULL
           AND new_entity_id IS DISTINCT FROM old_entity_id THEN
            PERFORM catalog.assert_verified_node(new_entity_id);
        END IF;
    END IF;

    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION evidence.check_verified_relationship_trigger()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    old_relationship_id uuid;
    new_relationship_id uuid;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        old_relationship_id := OLD.relationship_id;
        PERFORM evidence.assert_verified_relationship(old_relationship_id);
    END IF;

    IF TG_OP <> 'DELETE' THEN
        new_relationship_id := NEW.relationship_id;
        IF new_relationship_id IS DISTINCT FROM old_relationship_id THEN
            PERFORM evidence.assert_verified_relationship(new_relationship_id);
        END IF;
    END IF;

    RETURN NULL;
END;
$$;

CREATE FUNCTION evidence.check_verified_source_trigger()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    affected_entity_id uuid;
    affected_relationship_id uuid;
BEGIN
    FOR affected_relationship_id IN
        SELECT DISTINCT relationship_id
        FROM evidence.relationship_sources
        WHERE source_id = NEW.source_id
    LOOP
        PERFORM evidence.assert_verified_relationship(affected_relationship_id);
    END LOOP;

    FOR affected_entity_id IN
        SELECT DISTINCT status_history.entity_id
        FROM evidence.status_sources AS status_sources
        JOIN evidence.entity_status_history AS status_history
          ON status_history.status_id = status_sources.status_id
        WHERE status_sources.source_id = NEW.source_id
    LOOP
        PERFORM catalog.assert_verified_node(affected_entity_id);
    END LOOP;

    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER verified_source_substantive_ck
AFTER UPDATE ON evidence.sources
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
WHEN (OLD.is_substantive IS DISTINCT FROM NEW.is_substantive)
EXECUTE FUNCTION evidence.check_verified_source_trigger();
