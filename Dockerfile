# syntax=docker/dockerfile:1

ARG PYTHON_IMAGE=python:3.13-slim-bookworm@sha256:281d39ff02e3b389401586134ff9e6572954687822a58055ec07a60ded4e0b7f

# --- builder: resolve dependencies into a venv we can copy as a unit ---------
FROM ${PYTHON_IMAGE} AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Without a WORKDIR the project would be built from `/`, and setuptools would
# crawl the whole container filesystem looking for packages.
WORKDIR /build

# Hash-checked install of the pinned dependency set. The project itself goes in
# a second step because hash-checking mode rejects local-directory installs.
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock

# Installs the app/ and spiders/ packages plus the dist metadata that main.py
# reads for the version banner.
COPY pyproject.toml ./
COPY app ./app
COPY spiders ./spiders
RUN pip install --no-deps .

# --- runtime ----------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

COPY --from=builder /opt/venv /opt/venv

# Chromium and its system libraries are only needed by the MercadoLibre spider,
# but one image keeps the compose file simple. The browser goes in a shared path
# (not the user's home) so the non-root user below can read it.
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 app \
    && mkdir /app \
    && chown app:app /app

USER app
WORKDIR /app

# dbt writes target/ and logs/ under analytics/, hence the app-owned tree.
COPY --chown=app:app main.py ./
COPY --chown=app:app jobs ./jobs
COPY --chown=app:app analytics ./analytics
COPY --chown=app:app sql ./sql

CMD ["python", "main.py"]
