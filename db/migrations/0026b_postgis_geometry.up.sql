-- Task 26b -- OPTIONAL native PostGIS geometry. NOT executed in the current environment: postgres:15 has no PostGIS
-- extension (pg_available_extensions has no 'postgis'). Written, structure-tested and ready for a PostGIS-enabled server.
-- Guarded: on a server without PostGIS it raises a NOTICE and does nothing, so applying it can never half-apply.
-- Adds a derived geometry column next to geometry_geojson (the GeoJSON stays the audit copy). Idempotent.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'postgis') THEN
        RAISE NOTICE 'PostGIS is not available on this server; 0026b skipped (nothing changed)';
        RETURN;
    END IF;
    CREATE EXTENSION IF NOT EXISTS postgis;
    EXECUTE 'ALTER TABLE geo.boundary_admin_unit ADD COLUMN IF NOT EXISTS geom geometry(MultiPolygon, 4326)';
    EXECUTE $q$UPDATE geo.boundary_admin_unit
                SET geom = ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(geometry_geojson::text), 4326))
                WHERE geometry_geojson IS NOT NULL AND geom IS NULL$q$;
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_boundary_unit_geom ON geo.boundary_admin_unit USING GIST (geom)';
    -- record (never repair) PostGIS' own validity verdict
    EXECUTE $q$UPDATE geo.boundary_admin_unit
                SET validation_notes = concat_ws('; ', validation_notes, 'postgis ST_IsValid=' || ST_IsValid(geom)::text)
                WHERE geom IS NOT NULL AND (validation_notes IS NULL OR validation_notes NOT LIKE '%postgis ST_IsValid%')$q$;
END
$$;
