# Rent Radar

Personal monitor of rental listings in Buenos Aires / Gran Buenos Aires. It
scrapes ZonaProp, ArgenProp and MercadoLibre, cleans and deduplicates the
listings with dbt, detects new listings and price changes, sends Telegram
notifications.

Support for sale listings and configurable searches is planned; today the
searches are fixed (see Configuration).

## Run it

Requires Docker with Compose.

```bash
cp .env.example .env     # set POSTGRES_PASSWORD (letters and digits only)
docker compose up -d
```

| Service | What it does | Address |
|---------|--------------|---------|
| `db` | PostgreSQL 17 | `127.0.0.1:5434` |
| `migrate` | Applies the `sql/` files the database has not seen yet, then exits | none |
| `prefect-server` | Prefect API and UI | http://127.0.0.1:4200 |
| `prefect-deploy` | Registers the work pool and deployments, then exits | none |
| `worker` | Runs the flows | none |

Everything is bound to loopback. To reach it from the LAN, change the bind
address of the `ports` entries in `docker-compose.yml`.

Once up, three flows run on their own schedule (`prefect.yaml`): ZonaProp and
ArgenProp every 10 minutes, MercadoLibre every hour, and a daily cleanup that
deletes snapshots older than 7 days.

One-off commands run in the same image:

```bash
docker compose run --rm app python jobs/run_dbt.py
docker compose run --rm app python main.py --ingest --source argenprop \
  --max-pages 1 --start-url "<search url>"
```

## Configuration

- `.env`: database credentials and, optionally, `TELEGRAM_BOT_TOKEN` and
  `TELEGRAM_CHAT_ID`. Without Telegram the `notify` and `check_health` steps
  fail every cycle; the rest of the pipeline keeps running.
- What to look for: `searches.yaml` (operation, neighborhoods, property types,
  rooms, price, page limits). It is read on every cycle, so an edit needs no
  restart. ZonaProp and ArgenProp URLs are generated from it; MercadoLibre takes
  the `urls` written in the file. Only one search can be active for now.
- Neighborhood names per portal: `neighborhoods.yaml`. Add an entry only after
  checking the slug on the live portal.
- Schema changes: add a numbered file to `sql/`. The `migrate` service applies
  it on the next `docker compose up` (applied files are recorded in
  `public.schema_migrations`).

## How it fits together

```
spiders -> raw.snapshots -> dbt -> silver.publicaciones -> gold.candidatas
                                         |
                      detect_events -> silver.events -> Telegram
```

## Known limitations

- The portals apply anti-bot protection. ArgenProp answered a burst of
  requests with an empty CloudFront challenge, and the spider records that run
  as `empty`. Keep search volume and frequency modest.
- `NEON_DATABASE_URL` keeps its upstream name but points at the local database.

## Origins

Fork of [NotoFederico/rent_radar](https://github.com/NotoFederico/rent_radar)
(MIT, Copyright (c) 2025 Federico Noto), forked at commit `608f241`. It no
longer tracks upstream. See `LICENSE`.
