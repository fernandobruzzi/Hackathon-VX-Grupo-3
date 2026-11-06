# syntax=docker/dockerfile:1
FROM node:20-slim AS front-build
ARG NEXT_PUBLIC_DATA_SOURCE=api
ENV NEXT_PUBLIC_DATA_SOURCE=$NEXT_PUBLIC_DATA_SOURCE
WORKDIR /app/front
COPY front/package.json front/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY front/ ./
RUN npm run build

FROM python:3.12-slim AS python-base
RUN pip install --no-cache-dir uv==0.11.16
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv PATH=/app/.venv/bin:$PATH UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
COPY back/pyproject.toml back/pyproject.toml
COPY mcp/pyproject.toml mcp/pyproject.toml
COPY api/pyproject.toml api/pyproject.toml
RUN useradd --create-home app

FROM scratch AS source
COPY back/ back/
COPY mcp/ mcp/
COPY api/ api/

FROM python-base AS api-build
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-workspace --package vx-materials-api
COPY --from=source / /app/
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable --package vx-materials-api

FROM python-base AS agent-build
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-workspace --package vx-materials-mcp
COPY --from=source / /app/
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable --package vx-materials-mcp

FROM python-base AS batch-build
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-workspace --package vx-materials-back
COPY --from=source / /app/
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable --package vx-materials-back

FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PATH=/app/.venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data/desafio01 PDM_WORKBOOK_PATH=/app/data/desafio01/03_padrao_cadastro_PDM.xlsx
RUN useradd --create-home app && mkdir /storage && chown app /storage
COPY data/desafio01/ /app/data/desafio01/
ADD --chmod=0444 --checksum=sha256:90a6f1a7978a1b1b096dca6c57511ca48d3b8cf052f8e704baf358f34ea2f21b \
    https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem /app/certs/rds-global-bundle.pem
RUN chmod 0755 /app/certs
USER app

FROM runtime AS api
COPY --from=api-build /app/.venv /app/.venv
COPY --from=front-build /app/front/out /app/front_dist
ENV FRONT_DIST_DIR=/app/front_dist
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('API_PORT','8000')+'/api/v1/healthz',timeout=2)"
CMD ["vx-api"]

FROM runtime AS agent
COPY --from=agent-build /app/.venv /app/.venv
EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('AGENT_PORT','8001')+'/healthz',timeout=2)"
CMD ["vx-agent"]

FROM runtime AS batch
COPY --from=batch-build /app/.venv /app/.venv
CMD ["vx-back", "--help"]
