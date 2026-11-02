# Rent Radar

Emails you when a new rental or sale listing that matches what you are looking
for appears on ZonaProp, ArgenProp or MercadoLibre in Buenos Aires / Gran Buenos
Aires. It has no UI of its own: everything is configured in `alerts.yaml`.

## How it works

```
spiders -> raw.snapshots -> dbt -> gold.candidatas -> send_alerts -> email (Apprise)
```

1. Every cycle the spiders scrape the searches in `alerts.yaml`. ZonaProp and
   ArgenProp URLs are generated from each alert; MercadoLibre takes the URLs
   written in the file.
2. dbt cleans and deduplicates the listings and keeps those that meet each
   alert's own criteria (rooms, area, garage, price).
3. A listing is new for an alert when it has not been seen before. The first
   listings of an alert on a portal are recorded without sending anything, so a
   new alert does not email everything that already exists.
4. New listings are emailed through Apprise, one email per cycle (`digest`) or
   one per listing (`each`). A message is marked as sent only once Apprise
   accepted it; a failed one is retried on the next cycle.
5. If a portal stops returning data (blocked, down) you get one email about it,
   and another when it recovers.

## Run it

Requires Docker with Compose.

```bash
cp .env.example .env     # set POSTGRES_PASSWORD (letters and digits only)
# put one Apprise URL in the file named by APPRISE_URL_FILE (see Configuration)
docker compose up -d
```

| Service | What it does | Address |
|---------|--------------|---------|
| `db` | PostgreSQL 17 | `127.0.0.1:5434` |
| `migrate` | Applies the `sql/` files the database has not seen yet, then exits | none |
| `prefect-server` | Prefect API and UI | http://127.0.0.1:4200 |
| `prefect-deploy` | Registers the work pool and deployments, then exits | none |
| `worker` | Runs the flows | none |
| `mailpit` | Catches emails locally (profile `dev`, off by default) | http://127.0.0.1:8025 |

Everything is bound to loopback. Three flows run on their own schedule
(`prefect.yaml`):

- `rent-radar`, every 10 minutes: sync `alerts.yaml`, scrape ZonaProp and
  ArgenProp, run dbt, send the alerts, check the portals' health.
- `rent-radar-mercadolibre`, every hour: scrape MercadoLibre (slow, with
  anti-bot pauses).
- `rent-radar-prune`, daily at 08:00 Buenos Aires: delete snapshots older than
  7 days.

## Configuration

- **`alerts.yaml`** is the only file you edit. It is read on every cycle, so a
  change needs no restart. It has three parts:
  - `apprise.services`: where the alerts go. Each service points at a file
    holding one Apprise URL (`url_file`), because the URL carries a password
    and must stay out of git. For Gmail the file holds
    `mailto://user:app-password@gmail.com?to=you@example.com`.
  - `health.enabled`: the email about portals that stop returning data.
  - `alerts`: what to look for. Each alert has an `id`, an `operation` (`rent`,
    `sale` or `both`), a `delivery` (`digest` or `each`), `neighborhoods`,
    `property_types`, `rooms`, optional `min_garage` and `min_area_m2`, a
    `price` (`currency` and `max`), and the `portals` to scrape with their
    `max_pages` and optional `urls`. With `operation: both`, `price` has a
    `rent` and a `sale` entry, and pasted `urls` are not allowed because a URL
    belongs to one operation.
- **`neighborhoods.yaml`**: each neighborhood as the portals name it in their
  URLs. Add an entry only after checking the slug on the live portal; a wrong
  one makes a portal silently search somewhere else.
- **`.env`**: the database credentials and `APPRISE_URL_FILE`, the path of the
  Apprise URL file on the host.

## Development

- Emails locally: `docker compose --profile dev up -d mailpit`, and put
  `mailto://radar:pass@mailpit:1025?mode=insecure&to=you@example.com&from=radar@example.com`
  in the Apprise URL file. The emails show up at http://127.0.0.1:8025.
- One-off commands run in the same image, for example
  `docker compose run --rm app python jobs/run_ingest.py --source zonaprop`
  or `docker compose run --rm app python jobs/send_alerts.py`.
- Schema changes: add a numbered file to `sql/`. The `migrate` service applies
  it on the next `docker compose up` and records it in
  `public.schema_migrations`.
- Dependencies are pinned with hashes in `requirements.lock`.

## Known limitations

- **ArgenProp** answers some clients with an AWS WAF challenge that the plain
  HTTP spider cannot pass. The run is recorded as `empty` and the health alert
  tells you.
- **MercadoLibre** has no URL builder: it needs `urls` in the alert, and a
  pasted URL covers one operation and one set of neighborhoods.
- Only **new listings** are alerted: no price changes, no listings that went
  off the market.
- The same property on two portals is only recognised as one when both listings
  have coordinates, so it can arrive twice.
- The Prefect UI has no authentication. Keep it on a trusted network.
- `NEON_DATABASE_URL` keeps its upstream name but points at the local database.

## Origins

Fork of [NotoFederico/rent_radar](https://github.com/NotoFederico/rent_radar)
(MIT, Copyright (c) 2025 Federico Noto), forked at commit `608f241`. It no
longer tracks upstream. See `LICENSE`.
