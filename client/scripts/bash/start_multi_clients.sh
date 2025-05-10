#!/bin/bash
#===================================================================================
# Dropbox System - Start Multiple Clients (Device A and Device B)
#===================================================================================
# Description: This script starts two client containers (Device A and Device B)
# for the Dropbox system.
#
# Usage: ./client/scripts/bash/start_multi_clients.sh [options]
#   Options:
#     --clean       Remove all client containers and volumes before starting
#     --help        Display this help message
#
#===================================================================================

# Set text colors for better readability
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default settings
DO_CLEAN=false
NETWORK_NAME="dropbox-network"
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)")

# Process command line arguments
for arg in "$@"; do
  case $arg in
    --clean)
      DO_CLEAN=true
      shift
      ;;
    --help)
      echo -e "${CYAN}Dropbox System - Start Multiple Clients${NC}"
      echo -e "Usage: ./client/scripts/bash/start_multi_clients.sh [options]"
      echo -e "  Options:"
      echo -e "    --clean       Remove all client containers and volumes before starting"
      echo -e "    --help        Display this help message"
      exit 0
      ;;
    *)
      # Unknown option
      echo -e "${RED}Unknown option: $arg${NC}"
      echo -e "Use --help for usage information"
      exit 1
      ;;
  esac
done

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    echo -e "Please start Docker and try again"
    exit 1
fi

# Check if the network exists, create it if it doesn't
if ! docker network ls | grep -q $NETWORK_NAME; then
    echo -e "${YELLOW}Creating Docker network: $NETWORK_NAME${NC}"
    docker network create $NETWORK_NAME
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Network created successfully${NC}"
    else
        echo -e "${RED}Failed to create network${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}Network $NETWORK_NAME already exists${NC}"
fi

# Clean up if requested
if [ "$DO_CLEAN" = true ]; then
    echo -e "${YELLOW}Stopping client containers...${NC}"
    docker compose -f $PROJECT_ROOT/deployment/client/docker-compose-multi.yml down 2>/dev/null

    echo -e "${YELLOW}Removing client volumes...${NC}"
    docker compose -f $PROJECT_ROOT/deployment/client/docker-compose-multi.yml down -v 2>/dev/null
fi

# Start client containers
echo -e "${YELLOW}Starting client containers (Device A and Device B)...${NC}"
cd $PROJECT_ROOT/deployment/client
docker compose -f docker-compose-multi.yml up -d

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Client containers started successfully!${NC}"
    
    # Display service URLs
    echo -e "\n${CYAN}Client URLs:${NC}"
    echo -e "  - Device A API: ${GREEN}http://localhost:8000${NC}"
    echo -e "  - Device B API: ${GREEN}http://localhost:8010${NC}"
else
    echo -e "${RED}Failed to start client containers${NC}"
    exit 1
fi

echo -e "${BLUE}=========================================${NC}"
exit 0
