# Rent Radar

Personal tool that emails Marc when a new rent or sale listing matching what he
is looking for appears on ZonaProp, ArgenProp, MercadoLibre or Más Hogares BNA in Buenos Aires /
Gran Buenos Aires. It has no UI: everything is configured in `config/alerts.yaml`.
Hard fork of [rent_radar](https://github.com/NotoFederico/rent_radar) (license:
MIT), forked at upstream commit 608f241877fdf6516ee161833eaa8b6de373695b.

Goal: run it reliably on Marc's homelab (see Workflow). Any other feature:
propose options and wait for Marc's decision before building it.

## Working with Marc

- Marc writes to you in Spanish; answer him in Spanish. Everything that stays
  in the repo is in English: code, identifiers, comments, commit messages,
  docs, READMEs.
- User-facing text (the alert emails): Spanish es-AR with voseo.
- Small, reviewable steps; he wants tight control. When a choice is
  architectural or changes behaviour (data model, permissions, flows,
  dependencies), lay out the options with a recommendation **before** writing
  code and wait for his answer.
- Don't bundle unrelated changes. If you notice something out of scope, say so
  rather than fixing it silently.
- Ask first before: deploying, touching production, deleting or wiping data,
  force-pushing, or any destructive command. Look at the target before
  deleting or overwriting.
- Report outcomes faithfully: if tests fail, say so with the output; if a step
  was skipped, say that.

## Fork status and license

This is now Marc's own project: a personal tool, run only on his homelab. It
started as a fork but no longer tracks upstream, so merge compatibility is not
a constraint: restructure, rename and rewrite upstream code freely when the
work calls for it.

- Do not add an `upstream` remote or merge upstream changes. Git history stays
  intact (never rewrite it).
- Keep `LICENSE` (MIT, Copyright (c) 2025 Federico Noto) unchanged, and keep an
  "Origins" note in the README crediting the upstream project.
- Spiders are the one part to evolve rather than rewrite: they hold the
  hard-won anti-bot handling. Everything around them (schema, search
  configuration, orchestration, alerts) can be rebuilt.
- Read the existing code before replacing it; the comments record real
  incidents (blocks, outages), and a rewrite must keep those fixes.
- Don't reformat unrelated code while making a change; one concern per commit.

## Stack and commands

- Python 3.13 (`requires-python >=3.13`; the host has only 3.9, so everything
  runs in Docker). Prefect (orchestration), dbt-postgres (silver/gold
  transforms), Playwright + `curl_cffi` + `requests`/BeautifulSoup (spiders),
  psycopg2, Apprise (email alerts).
- Dependencies are pinned with hashes in `requirements.lock`. After changing
  `pyproject.toml`, regenerate it with `uv pip compile pyproject.toml
  --universal --generate-hashes --python-version 3.13 --no-header` inside a
  `python:3.13-slim-bookworm` container, starting from a copy of the current
  lock so unrelated versions do not move.
- Database: PostgreSQL 17 in Docker. Schema changes are numbered files in
  `sql/`, applied by the `migrate` service; a removed dbt model's table must be
  dropped by a migration, dbt does not do it.
- Configuration lives in `config/`, mounted whole into the containers (a mounted
  single file goes stale when git or an editor replaces it): `alerts.yaml`
  (git-ignored; alerts, Apprise services, health; sample in
  `alerts.example.yaml`) and `neighborhoods.yaml` (each neighborhood as the
  portals name it, only entries checked against the live portal).
  Secrets: `.env` and `config/apprise-url.txt` (the Apprise URL), never the YAML.
- Install: `docker compose build` · Dev: `docker compose up -d`; add
  `--profile dev` for Mailpit (http://127.0.0.1:8025), which catches the emails
  locally.
- Test and lint/typecheck: none. Personal tool with no production; Marc decided
  automated tests are not required (the upstream project has none).

## Docker

- Multi-stage build, pinned base image versions, non-root user, `.dockerignore`.
- Config through environment variables; no secrets baked into images.
- `docker-compose.yml`: healthchecks, named volumes for data.
- This machine's Homebrew Postgres owns port 5432 (trust auth) and another
  project owns 5433: Postgres is published on 5434.
- Document how to build and run in the README.

## Workflow

- Commit directly to `master` (single developer, no upstream to mirror), one
  commit per concern.
- The Mac keeps no running stack and no local database: code is written here and
  tested on the homelab. Commit, `git push origin master`, wait for the image
  workflow (`gh run list --limit 1`), then on the server:
  `ssh home-server`, `cd /opt/stacks/rent-radar`,
  `git pull && docker compose pull && docker compose up -d`. Useful there:
  `docker compose logs --tail 50 worker`, and
  `docker compose exec worker prefect deployment run 'rent-radar/cada_10min'` to
  run a cycle now. A local `docker compose up` still works if a change needs it.
- `config/alerts.yaml` is personal and git ignores it; the repo carries
  `config/alerts.example.yaml`. It is edited on the server (or copied there),
  and the next cycle uses it with no pull, image or restart.
- Done: Docker; searches defined in YAML, one operation (rent or sale) per alert; email alerts
  through Apprise (replacing Telegram and the map dashboard); deployed on the
  homelab, where the ZonaProp alerts are running.
- Known state of the portals on the server: ZonaProp rent and sale work;
  ArgenProp now asks for the detail of new listings only, capped at 15 requests
  per run (written and tested against a fake portal, not yet watched on the
  server: check that its searches finish reading and that the cap is right);
  MercadoLibre reads prices on the server now (45 of 45 in the first runs) and its
  generated URLs work for GBA; the CABA ones (Saavedra, Coghlan) answer HTTP 404
  yet render their results (the spider now reads them; Coghlan casas answered 400). It asks for the detail of new listings only (written
  and tested against fake card markup, not yet watched on the server: check that
  the second run is fast and that prices still update from the results cards).
  Más Hogares BNA (`mashogares`, sale only) reads a JSON API with no browser; tested
  live from the Mac end to end against the local database and Mailpit, not yet
  watched on the server.
- Next, in order, one at a time:
  1. Watch ArgenProp on the server and tune `max_requests` if the WAF still cuts
     it off.
  2. MercadoLibre: confirm the CABA URLs now yield listings, and confirm on the server that known listings are reused.

## Git

- One commit per concern. Imperative subject under ~70 characters; the body
  says *why* and what was verified, not which files changed.
- Don't commit or push unless asked.
- Never commit secrets. They live in `.env` (gitignored), with a committed
  `.env.example` listing variable names only.

## Definition of done

- The stack comes up with `docker compose up` and the affected flow runs end to
  end against the local database (never against anything shared or real).
- Anything that sends email is checked against the dev Mailpit service, never a
  real mailbox.
- Say what was run and what was not; no automated tests exist by decision.

## Code style

- New code is in English and consistent with itself. When editing existing
  code, keep its comment density and idiom unless the change replaces it.
- No `any`, no dead code, no parameters or columns "for later".
- Comments explain *why* (the constraint, the bug it prevents, the decision),
  never what the line does. When fixing a subtle bug, leave its reason in the
  code.
- Names in full words, small functions, one reason to change per file. Prefer a
  pure function over logic inside a component or handler.
- Errors people see are specific and actionable, never a raw exception.

## Security

- The project listens on no network port of its own; the Prefect UI is
  LAN-only on the homelab. If anything is ever exposed beyond the LAN,
  authenticate it first; hiding a link is not protection.
- Secrets (the database password, the Apprise URL) live only in `.env` and in
  `config/apprise-url.txt`, and are never committed. Error messages and logs name
  the file or service, never the secret.
