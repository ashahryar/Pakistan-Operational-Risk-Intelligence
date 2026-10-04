-- Task 26b rollback: removes only the derived PostGIS column/index added by 0026b (the extension itself is left alone).
DROP INDEX IF EXISTS geo.ix_boundary_unit_geom;
ALTER TABLE IF EXISTS geo.boundary_admin_unit DROP COLUMN IF EXISTS geom;
