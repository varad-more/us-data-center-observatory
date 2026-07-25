-- Extensions required by the Helios schema, created before migrations run.
--
-- PostGIS provides geometry types, spatial indexing, and geodesic distance.
-- pg_trgm backs the trigram index used to block organization names during
-- entity resolution.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
