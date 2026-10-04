-- Task 26 rollback: removes ONLY the objects created by 0026_geo_serving_layer.up.sql (and 0026b if applied).
-- geo.admin_unit, geo.name_alias, geo.resolved_observation_counts and every existing table are untouched.
DROP VIEW IF EXISTS geo.operational_risk_map;
DROP VIEW IF EXISTS risk.latest_operational_risk;
DROP VIEW IF EXISTS geo.current_boundary;
DROP TABLE IF EXISTS risk.operational_risk;
DROP TABLE IF EXISTS geo.boundary_crosswalk;
DROP TABLE IF EXISTS geo.boundary_admin_unit;
DROP TABLE IF EXISTS geo.boundary_source;
DROP SCHEMA IF EXISTS risk;     -- raises (and aborts the rollback transaction) if anything else lives in it
