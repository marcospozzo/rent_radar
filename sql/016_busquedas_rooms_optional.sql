-- An alert may leave out `rooms`, which means any number of rooms.

ALTER TABLE silver.busquedas ALTER COLUMN ambientes_min DROP NOT NULL;
