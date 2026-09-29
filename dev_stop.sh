#!/bin/bash
#
# iTaxEasy APK Backend — stop the local dev environment (modeled on vm-api/dev_stop.sh).
# Tears down Docker containers and frees the dev ports.

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR" || exit 1

echo -e "${YELLOW}Stopping development environment...${NC}"
echo ""

# Stop infrastructure containers
docker compose -f docker-compose.dev.yml down

echo ""
echo -e "${YELLOW}Killing processes on development ports...${NC}"

# 3002 = FastAPI, 5432 = Postgres, 54332 = Redis
PORTS=(3002 5432 54332)
for port in "${PORTS[@]}"; do
    if lsof -i :$port -t > /dev/null 2>&1; then
        echo "Killing processes on port $port..."
        lsof -i :$port -t | xargs -r kill -9 2>/dev/null
    fi
done

echo ""
echo -e "${GREEN}✓ Development environment stopped${NC}"
echo -e "${GREEN}✓ All development ports cleared${NC}"
