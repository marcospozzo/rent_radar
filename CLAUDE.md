# Rent Radar

Personal tool that emails Marc when a new rent or sale listing matching what he
is looking for appears on ZonaProp, ArgenProp or MercadoLibre in Buenos Aires /
Gran Buenos Aires. It has no UI: everything is configured in `alerts.yaml`.
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
- Configuration: `alerts.yaml` (alerts, Apprise services, health), plus
  `neighborhoods.yaml` (each neighborhood as the portals name it, only entries
  checked against the live portal). Secrets: `.env` and the file holding the
  Apprise URL, never the YAML.
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
- Done: Docker; searches defined in YAML with rent, sale or both; email alerts
  through Apprise (replacing Telegram and the map dashboard).
- Next, in order, one at a time:
  1. Deploy to the homelab: amd64 image on GHCR, compose settings for the LAN,
     deployment notes in the README.
  2. ArgenProp: get past its AWS WAF challenge, which blocks the plain HTTP
     spider.
  3. Sale listings on ArgenProp and MercadoLibre, and a MercadoLibre URL
     builder.
- Open decisions to settle with Marc before coding: how to get past the
  ArgenProp challenge (a real browser is the likely answer).

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
  the Apprise URL file, and are never committed. Error messages and logs name
  the file or service, never the secret.
