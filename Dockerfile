# iTaxEasy APK backend (FastAPI)
# Runs the same way as prod (pm2 -> poetry run uvicorn app.main:app --port 54110 --workers 2),
# with all dependencies installed inside the image.

# Stage 1: install the locked production dependencies into an in-project venv
FROM python:3.12-slim AS dependencies

ENV PIP_NO_CACHE_DIR=1 \
  PIP_DISABLE_PIP_VERSION_CHECK=1 \
  POETRY_NO_INTERACTION=1 \
  POETRY_VIRTUALENVS_IN_PROJECT=true

# pyproject.toml pins requires-poetry ==2.2.1
RUN pip install "poetry==2.2.1"

WORKDIR /app
COPY pyproject.toml poetry.lock poetry.toml ./
RUN poetry install --only main --no-root

# Stage 2: runtime (no poetry, no build tools)
FROM python:3.12-slim AS runner

ENV PYTHONUNBUFFERED=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  PATH="/app/.venv/bin:$PATH" \
  PORT=54110 \
  WORKERS=2

WORKDIR /app
COPY --from=dependencies /app/.venv /app/.venv
COPY . .

# Precompile once here, so the read-only container never needs to write .pyc files
RUN python -m compileall -q app alembic

EXPOSE 54110

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS}"]
