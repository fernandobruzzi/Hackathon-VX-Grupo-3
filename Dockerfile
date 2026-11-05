FROM node:20-slim AS front-build
WORKDIR /app/front
COPY front/package.json front/package-lock.json ./
RUN npm ci
COPY front/ ./
RUN npm run build

FROM python:3.12-slim AS python-base
RUN pip install --no-cache-dir uv==0.11.16
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv PATH=/app/.venv/bin:$PATH
COPY pyproject.toml uv.lock ./
COPY back/ back/
COPY mcp/ mcp/
COPY api/ api/
RUN useradd --create-home app

FROM python-base AS api
RUN uv sync --locked --no-dev --no-editable --package vx-materials-api
COPY --from=front-build /app/front/out /app/front_dist
ENV FRONT_DIST_DIR=/app/front_dist
RUN mkdir /storage && chown app /storage
USER app
EXPOSE 8000
CMD ["vx-api"]

FROM python-base AS agent
RUN uv sync --locked --no-dev --no-editable --package vx-materials-mcp
USER app
EXPOSE 8001
CMD ["vx-agent"]

FROM python-base AS batch
RUN uv sync --locked --no-dev --no-editable --package vx-materials-back
USER app
CMD ["vx-back", "--help"]
