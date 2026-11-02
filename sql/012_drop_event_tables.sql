-- Alerts no longer compare runs to emit events: silver.avisos remembers what was
-- already sent. silver.events and silver.notifications held the Telegram-era
-- events and their delivery log; raw.events and raw.notifications were never
-- written to by the code that exists today.

DROP TABLE IF EXISTS silver.notifications;
DROP TABLE IF EXISTS silver.events;
DROP TABLE IF EXISTS raw.notifications;
DROP TABLE IF EXISTS raw.events;
