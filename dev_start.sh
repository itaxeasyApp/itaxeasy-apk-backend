#!/bin/bash
#
# iTaxEasy APK Backend — local dev environment (modeled on vm-api/dev_start.sh).
# Brings up Docker (Postgres + Redis), waits for health, runs the LATEST Alembic
# migrations, then starts the FastAPI server on :54110.

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'

RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}   iTaxEasy APK Backend — Development Environment${NC}"
echo -e "${BLUE}==================================================${NC}"
echo ""

# Run from the project root regardless of where the script is invoked from.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR" || exit 1

COMPOSE_FILE="docker-compose.dev.yml"
PG_CONTAINER="itaxeasy-apk-postgres"
APP_PORT=54110

# ── Step 1: Python + Poetry ───────────────────────────────────────────────
echo -e "${YELLOW}[1/5] Checking Python & Poetry...${NC}"

if ! command -v python3.12 &> /dev/null; then
    echo -e "${RED}Python 3.12 not found. Please install it first.${NC}"
    exit 1
fi

# Read the pinned Poetry version from pyproject.toml (single source of truth)
REQUIRED_POETRY_VERSION=$(grep '^requires-poetry' pyproject.toml | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')

POETRY_CMD=""
if command -v poetry &> /dev/null; then
    POETRY_CMD="poetry"
elif [ -f "$HOME/.local/bin/poetry" ]; then
    POETRY_CMD="$HOME/.local/bin/poetry"
fi

if [ -n "$POETRY_CMD" ] && [ -n "$REQUIRED_POETRY_VERSION" ]; then
    CURRENT_POETRY_VERSION=$($POETRY_CMD --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
    if [ "$CURRENT_POETRY_VERSION" != "$REQUIRED_POETRY_VERSION" ]; then
        echo -e "${YELLOW}Poetry ${CURRENT_POETRY_VERSION:-none} installed, need ${REQUIRED_POETRY_VERSION}. Reinstalling...${NC}"
        POETRY_CMD=""
    fi
fi

if [ -z "$POETRY_CMD" ]; then
    echo -e "${YELLOW}Installing Poetry ${REQUIRED_POETRY_VERSION:-latest}...${NC}"
    if [ -n "$REQUIRED_POETRY_VERSION" ]; then
        curl -sSL https://install.python-poetry.org | python3.12 - --version "$REQUIRED_POETRY_VERSION"
    else
        curl -sSL https://install.python-poetry.org | python3.12 -
    fi
    if [ -f "$HOME/.local/bin/poetry" ]; then
        POETRY_CMD="$HOME/.local/bin/poetry"
    else
        echo -e "${RED}Poetry installation failed.${NC}"
        exit 1
    fi
fi

$POETRY_CMD env use python3.12 &> /dev/null
echo -e "${YELLOW}Installing project dependencies...${NC}"
$POETRY_CMD install
if [ $? -ne 0 ]; then
    echo -e "${RED}Poetry install failed. Check pyproject.toml.${NC}"
    exit 1
fi

# macOS Gatekeeper can refuse unsigned .so files in the venv — strip quarantine.
if [[ "$(uname)" == "Darwin" ]]; then
    xattr -cr .venv 2>/dev/null || true
fi
echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# ── Step 2: .env ──────────────────────────────────────────────────────────
echo -e "${YELLOW}[2/5] Ensuring .env exists...${NC}"
if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${GREEN}✓ Created .env from .env.example (add your Firebase credentials).${NC}"
else
    echo -e "${GREEN}✓ .env already exists.${NC}"
fi
echo ""

# ── Step 3: Docker containers ─────────────────────────────────────────────
echo -e "${YELLOW}[3/5] Starting Docker containers (PostgreSQL + Redis)...${NC}"
docker compose -f "$COMPOSE_FILE" up -d
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to start containers. Is Docker running?${NC}"
    exit 1
fi

echo -e "${YELLOW}Waiting for PostgreSQL to be healthy...${NC}"
for i in {1..30}; do
    if docker exec "$PG_CONTAINER" pg_isready -U itaxeasy_apk_user -d itaxeasy_apk &> /dev/null; then
        echo -e "${GREEN}✓ PostgreSQL is ready${NC}"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo -e "${RED}PostgreSQL did not become ready in time.${NC}"
        exit 1
    fi
    sleep 1
done
echo ""

# ── Step 4: Migrations (always run the latest) ────────────────────────────
echo -e "${YELLOW}[4/5] Running database migrations...${NC}"
echo -e "${YELLOW}Current migration state:${NC}"
$POETRY_CMD run alembic current || echo "No migrations applied yet"

echo -e "${YELLOW}Running: alembic upgrade head${NC}"
$POETRY_CMD run alembic upgrade head
if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Migration failed! Check the alembic errors above.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Database schema is up to date${NC}"
echo ""

# ── Step 5: Start FastAPI ─────────────────────────────────────────────────
echo -e "${YELLOW}[5/5] Starting FastAPI server...${NC}"
if command -v lsof &> /dev/null; then
    PID=$(lsof -ti:$APP_PORT 2>/dev/null)
    if [ -n "$PID" ]; then
        echo -e "${YELLOW}Port $APP_PORT in use. Killing $PID...${NC}"
        kill -9 $PID 2>/dev/null || true
        sleep 1
    fi
fi

echo ""
echo -e "${BLUE}==================================================${NC}"
echo -e "${GREEN}Server starting on http://localhost:${APP_PORT}${NC}"
echo -e "${GREEN}Swagger docs: http://localhost:${APP_PORT}/docs${NC}"
echo -e "${BLUE}==================================================${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop the server (run ./dev_stop.sh to tear down Docker)${NC}"
echo ""

$POETRY_CMD run uvicorn app.main:app --host 0.0.0.0 --port $APP_PORT --reload
