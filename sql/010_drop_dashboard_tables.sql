-- The map dashboard is gone. silver.property_flags held its "me interesa /
-- descartada" marks and gold.metricas its summary numbers; nothing else reads
-- either. gold.metricas is built by dbt, which does not drop a removed model.

DROP TABLE IF EXISTS silver.property_flags;
DROP TABLE IF EXISTS gold.metricas;
