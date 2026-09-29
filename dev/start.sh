#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}   iTaxEasy Mobile APK Backend - Start Script${NC}"
echo -e "${BLUE}==================================================${NC}"
echo ""

# Ensure we are in the script directory's parent (project root)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR/.." || exit 1

# Step 1: Copy environment file if not exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}Creating .env file from .env.example...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✓ .env file created.${NC}"
else
    echo -e "${GREEN}✓ .env file already exists.${NC}"
fi

# Step 2: Install Poetry dependencies
echo -e "${YELLOW}Installing dependencies using Poetry...${NC}"
if ! command -v poetry &> /dev/null; then
    echo -e "${RED}Poetry is not installed. Please install it or use standard virtualenvs.${NC}"
    exit 1
fi

poetry install
if [ $? -ne 0 ]; then
    echo -e "${RED}Poetry install failed.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Dependencies installed.${NC}"

# Strip macOS Gatekeeper quarantine if applicable
if [[ "$(uname)" == "Darwin" ]]; then
    xattr -cr .venv 2>/dev/null || true
fi

# Step 3: Launch Local Docker Containers
echo -e "${YELLOW}Starting PostgreSQL and Redis containers...${NC}"
docker compose -f docker-compose.dev.yml up -d
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to start docker containers. Please make sure Docker is running.${NC}"
    exit 1
fi

# Wait for database to accept connections
echo -e "${YELLOW}Waiting for PostgreSQL to be healthy...${NC}"
until docker exec itaxeasy-apk-postgres pg_isready -U itaxeasy_apk_user -d itaxeasy_apk &> /dev/null; do
    echo -n "."
    sleep 1
done
echo ""
echo -e "${GREEN}✓ Database is healthy.${NC}"

# Step 4: Run Alembic migrations
echo -e "${YELLOW}Running database migrations...${NC}"
poetry run alembic upgrade head
if [ $? -ne 0 ]; then
    echo -e "${RED}Alembic migrations failed.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Database schema is up to date.${NC}"

# Step 5: Start FastAPI application
echo -e "${GREEN}==================================================${NC}"
echo -e "${GREEN}✓ Everything is ready! Starting dev server...${NC}"
echo -e "${GREEN}==================================================${NC}"
echo ""

poetry run uvicorn app.main:app --host 0.0.0.0 --port 3002 --reload
