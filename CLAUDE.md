# Rent Radar

Personal monitor of rent and sale listings in Buenos Aires / Gran Buenos Aires.
Hard fork of [rent_radar](https://github.com/NotoFederico/rent_radar) (license:
MIT), forked at upstream commit 608f241877fdf6516ee161833eaa8b6de373695b.

Goal: dockerize it, then make searches configurable and support sale listings
(see Workflow). Any other feature: propose options and wait for Marc's decision
before building it.

## Working with Marc

- Marc writes to you in Spanish; answer him in Spanish. Everything that stays
  in the repo is in English: code, identifiers, comments, commit messages,
  docs, READMEs.
- User-facing UI strings (dashboard, Telegram): Spanish es-AR with voseo.
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
  configuration, orchestration, dashboard) can be rebuilt.
- Read the existing code before replacing it; the comments record real
  incidents (blocks, outages, wrong geocodes), and a rewrite must keep those
  fixes.
- Don't reformat unrelated code while making a change; one concern per commit.

## Stack and commands

- Python 3.13 (`requires-python >=3.13`; the host has only 3.9, so everything
  runs in Docker). Prefect (orchestration), dbt-postgres (silver/gold
  transforms), Playwright + `curl_cffi` + `requests`/BeautifulSoup (spiders),
  psycopg2. Dependency versions are not pinned yet; pinning comes with the
  Docker step.
- Database: PostgreSQL 17 in Docker on the homelab (replaces Neon).
- Scope: rent and sale listings in Buenos Aires / Gran Buenos Aires from
  ZonaProp, ArgenProp and MercadoLibre. Any number of active searches, each
  defined as data (operation, neighbourhoods, price range, rooms, property
  type), not hardcoded.
- Install: `docker compose build` · Dev: `docker compose up` (both planned,
  they arrive with the Docker step).
- Test and lint/typecheck: none. Personal tool with no production; Marc decided
  automated tests are not required (the upstream project has none).

## Docker

- Multi-stage build, pinned base image versions, non-root user, `.dockerignore`.
- Config through environment variables; no secrets baked into images.
- `docker-compose.yml` for local dev: healthchecks, named volumes for data.
- This machine's Homebrew Postgres owns port 5432 (trust auth): containers must
  publish Postgres on 5433 or another free port.
- Document how to build and run in the README.

## Workflow

- Commit directly to `master` (single developer, no upstream to mirror), one
  commit per concern.
- Planned changes, in order, one at a time:
  1. Docker: image, compose, local Postgres, dbt profile, Prefect services.
  2. Data model with `operation` (rent/sale) and searches defined in a YAML
     file, with a search id flowing through the whole pipeline.
  3. Spiders adapted to sale listings on the three portals.
  4. Dashboard and Telegram per search.
- Open decisions to settle with Marc before coding: the exact YAML format of a
  search (step 2).

## Git

- One commit per concern. Imperative subject under ~70 characters; the body
  says *why* and what was verified, not which files changed.
- Don't commit or push unless asked.
- Never commit secrets. They live in `.env` (gitignored), with a committed
  `.env.example` listing variable names only.

## Definition of done

- The stack comes up with `docker compose up` and the affected flow runs end to
  end against the local database (never against anything shared or real).
- Say what was run and what was not; no automated tests exist by decision.
- For UI, load the page and look at what renders; passing types say nothing
  about layout.

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

- Always validate every id and value on the server, and never serve the project
  directory or files holding secrets.
- Endpoints are LAN-only on the homelab. If any service is ever exposed beyond
  the LAN, authenticate and authorize each endpoint first; hiding a link is not
  protection.
- Secrets live only in `.env` and are never committed.
