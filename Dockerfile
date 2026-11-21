# One Dockerfile, two images:
#   docker build --target server .     -> API, worker, alerter, migrations
#   docker build --target dashboard .  -> Streamlit dashboard
# Usually you don't build by hand: `docker compose --profile app up --build`.

FROM python:3.15-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
RUN useradd --create-home --uid 1000 app


FROM base AS server
# 1) Install third-party deps only. This layer is cached until uv.lock changes,
#    so editing our own code doesn't re-download everything.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=sdk/pyproject.toml,target=sdk/pyproject.toml \
    --mount=type=bind,source=server/pyproject.toml,target=server/pyproject.toml \
    --mount=type=bind,source=dashboard/pyproject.toml,target=dashboard/pyproject.toml \
    uv sync --locked --no-dev --no-install-workspace --package llmwatch-server
# 2) Copy our code and install it.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package llmwatch-server
USER app
EXPOSE 8000
CMD ["uvicorn", "llmwatch_server.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]


FROM base AS dashboard
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=sdk/pyproject.toml,target=sdk/pyproject.toml \
    --mount=type=bind,source=server/pyproject.toml,target=server/pyproject.toml \
    --mount=type=bind,source=dashboard/pyproject.toml,target=dashboard/pyproject.toml \
    uv sync --locked --no-dev --no-install-workspace --package llmwatch-dashboard
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package llmwatch-dashboard
USER app
EXPOSE 8501
CMD ["streamlit", "run", "dashboard/src/llmwatch_dashboard/app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
