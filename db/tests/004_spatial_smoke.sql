DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM catalog.entities AS entities
        JOIN catalog.node_geometries AS node_geometries
          ON node_geometries.node_id = entities.entity_id
        WHERE entities.code = 'n-piraeus-port'
          AND node_geometries.geometry_role = 'centroid'
          AND node_geometries.is_current
          AND ST_Intersects(
              node_geometries.geom,
              ST_MakeEnvelope(23.50, 37.80, 23.75, 38.05, 4326)
          )
    ) THEN
        RAISE EXCEPTION 'Piraeus node was not found within the supplied AOI';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM catalog.entities AS entities
        JOIN catalog.corridor_geometries AS corridor_geometries
          ON corridor_geometries.corridor_id = entities.entity_id
        WHERE entities.code = 'cor-msr'
          AND corridor_geometries.is_current
          AND ST_Intersects(
              corridor_geometries.route_geometry,
              ST_MakeEnvelope(31.50, 29.50, 33.00, 32.00, 4326)
          )
    ) THEN
        RAISE EXCEPTION
            'Maritime Silk Road did not intersect the supplied Suez chokepoint geometry';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM catalog.entities AS entities
        JOIN catalog.node_geometries AS node_geometries
          ON node_geometries.node_id = entities.entity_id
        WHERE entities.code = 'n-piraeus-port'
          AND node_geometries.geometry_role = 'centroid'
          AND node_geometries.is_current
          AND ST_DWithin(
              node_geometries.geom::geography,
              ST_SetSRID(ST_MakePoint(23.62, 37.94), 4326)::geography,
              5000
          )
    ) THEN
        RAISE EXCEPTION 'global-distance proximity query did not find Piraeus';
    END IF;
END;
$$;
