DO $$
DECLARE
    missing_indexes text;
    promotion_rejected boolean := false;
BEGIN
    SELECT string_agg(expected.index_name, ', ' ORDER BY expected.index_name)
    INTO missing_indexes
    FROM (
        VALUES
            ('node_geometries_centroid_gix'),
            ('node_geometries_area_gix'),
            ('node_geometries_route_gix'),
            ('node_geometries_centroid_geography_gix'),
            ('corridor_geometries_route_gix'),
            ('imagery_assets_footprint_gix')
    ) AS expected(index_name)
    LEFT JOIN pg_indexes
      ON pg_indexes.indexname = expected.index_name
    WHERE pg_indexes.indexname IS NULL;

    IF missing_indexes IS NOT NULL THEN
        RAISE EXCEPTION 'missing spatial indexes: %', missing_indexes;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'observation'
          AND table_name = 'imagery_assets'
          AND data_type = 'bytea'
    ) THEN
        RAISE EXCEPTION 'imagery_assets must not contain binary image columns';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM geometry_columns
        WHERE f_table_schema = 'catalog'
          AND f_table_name = 'node_geometries'
          AND f_geometry_column = 'geom'
          AND srid = 4326
    ) THEN
        RAISE EXCEPTION 'catalog.node_geometries.geom is not registered as EPSG:4326';
    END IF;

    BEGIN
        UPDATE catalog.entities
        SET record_status = 'verified', last_verified_on = DATE '2026-08-02'
        WHERE code = 'n-lianyungang-port';

        PERFORM catalog.assert_verified_node(entity_id)
        FROM catalog.entities
        WHERE code = 'n-lianyungang-port';
    EXCEPTION WHEN raise_exception THEN
        promotion_rejected := true;
    END;

    IF NOT promotion_rejected THEN
        RAISE EXCEPTION
            'verified node promotion without verified substantive evidence was accepted';
    END IF;
END;
$$;
