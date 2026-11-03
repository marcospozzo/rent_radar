-- A search can now ask for a minimum price as well as a maximum one.

ALTER TABLE silver.busquedas ADD COLUMN IF NOT EXISTS precio_min NUMERIC;
