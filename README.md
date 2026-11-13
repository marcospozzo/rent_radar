# Rent Radar

Emails you when a new rental or sale listing that matches what you are looking
for appears on ZonaProp, ArgenProp, MercadoLibre or Más Hogares BNA in Buenos Aires /
Gran Buenos Aires. It has no UI of its own: everything is configured in `config/alerts.yaml`.

## How it works

```
spiders -> raw.snapshots -> dbt -> gold.candidatas -> send_alerts -> email (Apprise)
```

1. Every cycle the spiders scrape the searches in `config/alerts.yaml`. The URLs
   of each portal are generated from each alert.
2. dbt cleans and deduplicates the listings and keeps those that meet each
   alert's own criteria (rooms, area, garage, price).
3. A listing is new for an alert when it has not been seen before. The first
   listings of an alert on a portal are recorded without sending anything, so a
   new alert does not email everything that already exists. That silence lasts
   until a run of the alert on that portal has read everything it matches, which
   takes several cycles on ArgenProp (see Known limitations).
4. New listings are emailed through Apprise, one email per cycle (`digest`) or
   one per listing (`each`). A message is marked as sent only once Apprise
   accepted it; a failed one is retried on the next cycle.
5. If a portal stops returning data (blocked, down) you get one email about it,
   and another when it recovers.

## Run it

Requires Docker with Compose.

```bash
cp .env.example .env     # set POSTGRES_PASSWORD (letters and digits only)
cp config/alerts.example.yaml config/alerts.yaml    # then edit it (see Configuration)
# put one Apprise URL in config/apprise-url.txt (see Configuration)
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

- `rent-radar`, every 10 minutes: sync `config/alerts.yaml`, scrape ZonaProp,
  ArgenProp and Más Hogares BNA, run dbt, send the alerts, check the portals' health.
- `rent-radar-mercadolibre`, every hour: scrape MercadoLibre (slow, with
  anti-bot pauses).
- `rent-radar-prune`, daily at 08:00 Buenos Aires: delete snapshots older than
  7 days.

## Configuration

Everything lives in the `config/` folder, which the containers mount whole. Every
cycle re-reads it, so an edit, or a `git pull` that changes it, needs no restart.

- **`config/alerts.yaml`** is the only file you edit. It holds what you look for,
  which is personal, so git ignores it: start from `config/alerts.example.yaml`.
  It has four parts:
  - `apprise.services`: where the alerts go. Each service points at a file
    holding one Apprise URL (`url_file`), because the URL carries a password
    and must stay out of git. Keep it in `config/apprise-url.txt` (git ignores
    it), on one line and without quotes. For Gmail it is
    `mailto://user:app-password@gmail.com?to=you@example.com`. Several
    recipients go in `to=` separated by commas.
  - `health.enabled`: the email about portals that stop returning data.
  - `portals`: the portals every alert is looked up on (all four by default).
    Remove one from the list to switch it off, for instance while it blocks
    the scraper; its health email stops too. Más Hogares BNA only lists
    properties for sale, so rent alerts skip it.
  - `alerts`: what to look for. Each alert has an `id`, an `operation` (`rent`
    or `sale`), a `delivery` (`digest` or `each`), `neighborhoods`,
    `property_types`, `rooms`, optional `min_garage` and `min_area_m2`, a
    `price` (`currency` and an optional `min` and `max`). An alert is one
    operation; to look for both, write two alerts, which can differ in
    property types, rooms or neighborhoods. An optional `to` lists the
    addresses that alert's emails go to; without it they go to the address in
    the Apprise URL. That is how alerts for other people stay independent: each
    has its own `id` (prefix it with the person) and its own `to`, and their
    addresses live only in this git-ignored file. The health emails always go
    to the Apprise URL's address. A new alert starts silently (it records what
    already exists) and emails from the next cycle on.
- **`config/neighborhoods.yaml`**: each neighborhood as the portals name it in
  their URLs. Add an entry only after checking the slug on the live portal; a
  wrong one makes a portal silently search somewhere else.
- **`.env`**: the database credentials and, on a server, the image to run and
  the address to listen on.

## Development

- Emails locally: `docker compose --profile dev up -d mailpit`, and put
  `mailto://radar:pass@mailpit:1025?mode=insecure&to=you@example.com&from=radar@example.com`
  in `config/apprise-url.txt`. The emails show up at http://127.0.0.1:8025.
- One-off commands run in the same image, for example
  `docker compose run --rm app python jobs/run_ingest.py --source zonaprop`
  or `docker compose run --rm app python jobs/send_alerts.py`.
- Schema changes: add a numbered file to `sql/`. The `migrate` service applies
  it on the next `docker compose up` and records it in
  `public.schema_migrations`.
- Dependencies are pinned with hashes in `requirements.lock`.

## Deploy on a server

The image is built for `linux/amd64` and published to GitHub Container Registry
by `.github/workflows/docker.yml` on every push to master, tagged with the short
commit SHA and `latest`. The server only needs Docker Engine with Compose; it
pulls the image and reads `config/` from a clone of this repository.

To publish by hand instead (from an ARM Mac the emulated build takes a while):

```bash
docker login ghcr.io -u <github-user>      # password: a token with write:packages
TAG=$(git rev-parse --short HEAD)
docker buildx build --platform linux/amd64 \
  -t ghcr.io/marcospozzo/rent-radar:$TAG -t ghcr.io/marcospozzo/rent-radar:latest \
  --push .
```

On the server:

```bash
sudo mkdir -p /opt/stacks/rent-radar && sudo chown "$USER":"$USER" /opt/stacks/rent-radar
git clone https://github.com/marcospozzo/rent_radar.git /opt/stacks/rent-radar
cd /opt/stacks/rent-radar
cp .env.example .env
cp config/alerts.example.yaml config/alerts.yaml    # then edit it
# in .env set POSTGRES_PASSWORD, and uncomment RENT_RADAR_IMAGE (pin the tag if you
# want), BIND_ADDRESS=0.0.0.0 and PUBLIC_HOST (the server's IP or name)
# put the Apprise URL in config/apprise-url.txt, readable by the container user (uid 1000):
chmod 640 config/apprise-url.txt && sudo chown 1000:1000 config/apprise-url.txt
docker login ghcr.io -u <github-user>      # only if the package is private (token: read:packages)
docker compose pull
docker compose up -d
```

- **Update:** `git pull && docker compose pull && docker compose up -d`.
  `migrate` applies new migrations and `prefect-deploy` registers the flows again.
  A change to `config/alerts.yaml` needs nothing at all: git ignores it, so edit
  it on the server and the next cycle uses it.
- **First cycles:** the alerts start in silence (each alert's existing listings
  are recorded, not emailed). A portal with no successful run yet, such as
  MercadoLibre before its first hourly run, or one that is blocked, sends one
  health email and another when it recovers.
- **Backups:** nothing here is hard to replace. If the database is lost, the next
  start records what already exists without emailing it. `docker compose exec db
  pg_dump -U <user> <db>` is enough if you still want a copy.
- The Prefect UI is open to anyone on the LAN once `BIND_ADDRESS` is `0.0.0.0`.

## Known limitations

- **ArgenProp** answers a client past about twenty requests with an AWS WAF
  challenge. A run is capped at 15 requests (`max_requests` in
  `spiders/argenprop.py`, results pages and detail pages together) and asks for
  the detail page of new listings only: it reuses what it stored about the ones
  it has seen, and stops paging at the first page with nothing new. A search with
  many unseen listings therefore takes several cycles to read them all; the
  next run continues, and the alert stays silent until it has. A run that gets
  nothing back at all is recorded as `empty` and the health alert tells you.
- **ZonaProp with a price in dollars** (typically a sale alert, a `min` or a `max`)
  does not return listings with six or more rooms. Written as "N rooms or more", that price makes
  ZonaProp drop neighborhoods from the search, so the rooms go as a range up to 5.
  A price in pesos does not have this problem.
- **MercadoLibre** covers one property type in one place per URL, so an alert is
  one URL for each type and neighborhood, and a run takes a long time: it opens
  every listing in a browser with pauses between them. Its URLs were written from
  examples copied out of its page and have not run against the live portal; a
  maximum number of rooms and a minimum price without a maximum are left to dbt,
  because no URL form for them was checked. A wrong URL searches somewhere else
  and the results page is not checked against the neighborhoods, as ZonaProp's
  and ArgenProp's are.
- **Más Hogares BNA** (`mashogares`) is read from the JSON API its pages use, not
  from HTML, and only for sale alerts. It cannot filter by several property types
  or room counts at once, so an alert makes one request per type and dbt applies
  rooms and price. Its place filter matches by substring: "Florida" also brings
  Florida Oeste and Villa La Florida, and the spider keeps only the exact
  neighborhoods asked for. A neighborhood needs its province in
  `config/neighborhoods.yaml` (`mashogares`), because without it the portal
  ignores the filter and answers with the whole country; the spider fails the
  run if that happens. Listings marked as reserved are still alerted.
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
