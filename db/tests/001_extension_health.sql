DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_extension WHERE extname = 'postgis'
    ) THEN
        RAISE EXCEPTION 'PostGIS extension is not installed';
    END IF;
END;
$$;

SELECT current_database() AS database_name, PostGIS_Full_Version() AS postgis_version;
