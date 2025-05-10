#!/bin/bash
#===================================================================================
# Dropbox System - Start All Containers
#===================================================================================
# Description: This script starts all containers required for the Dropbox system
# in the correct order, ensuring dependencies are met before proceeding.
#
# The script will:
# 1. Create the shared Docker network if it doesn't exist
# 2. Start AWS services (S3, DynamoDB, API Gateway)
# 3. Start backend services (files-service, sync-service)
# 4. Start the client container
#
# Usage: ./client/scripts/bash/run_all_containers.sh [options]
#   Options:
#     --clean       Remove all containers and volumes before starting
#     --help        Display this help message
#
# Author: Kaveen Jayamanna
# Date: May 15, 2025
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
      echo -e "${CYAN}Dropbox System - Start All Containers${NC}"
      echo -e "Usage: ./client/scripts/bash/run_all_containers.sh [options]"
      echo -e "  Options:"
      echo -e "    --clean       Remove all containers and volumes before starting"
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

#===================================================================================
# Helper Functions
#===================================================================================

# Function to display step header
display_step() {
    local step_num=$1
    local step_desc=$2
    echo -e "\n${BLUE}=========================================${NC}"
    echo -e "${YELLOW}Step $step_num: $step_desc${NC}"
    echo -e "${BLUE}=========================================${NC}"
}

# Function to check if a container is running
is_container_running() {
    local container_name=$1
    if docker ps | grep -q $container_name; then
        return 0  # Container is running
    else
        return 1  # Container is not running
    fi
}

# Function to wait for a container to be healthy
wait_for_container() {
    local container_name=$1
    local max_wait=$2
    local wait_time=0
    local wait_interval=5

    echo -e "${YELLOW}Waiting for $container_name to be ready...${NC}"

    while [ $wait_time -lt $max_wait ]; do
        if is_container_running $container_name; then
            echo -e "${GREEN}✓ $container_name is running${NC}"
            return 0
        fi

        echo -e "${YELLOW}Waiting for $container_name... ($wait_time/$max_wait seconds)${NC}"
        sleep $wait_interval
        wait_time=$((wait_time + wait_interval))
    done

    echo -e "${RED}✗ Timed out waiting for $container_name${NC}"
    return 1
}

#===================================================================================
# Main Script
#===================================================================================

echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}Dropbox System - Start All Containers${NC}"
echo -e "${BLUE}=========================================${NC}"
echo -e "${CYAN}Project root: $PROJECT_ROOT${NC}"

# Clean up if requested
if [ "$DO_CLEAN" = true ]; then
    display_step 0 "Cleaning up existing containers and volumes"

    echo -e "${YELLOW}Stopping all containers...${NC}"
    docker compose -f $PROJECT_ROOT/deployment/client/docker-compose-multi.yml down 2>/dev/null
    docker compose -f $PROJECT_ROOT/deployment/backend/docker-compose.yml down 2>/dev/null
    docker compose -f $PROJECT_ROOT/deployment/aws/docker-compose.yml down 2>/dev/null

    echo -e "${YELLOW}Removing all volumes...${NC}"
    docker compose -f $PROJECT_ROOT/deployment/client/docker-compose-multi.yml down -v 2>/dev/null
    docker compose -f $PROJECT_ROOT/deployment/backend/docker-compose.yml down -v 2>/dev/null
    docker compose -f $PROJECT_ROOT/deployment/aws/docker-compose.yml down -v 2>/dev/null

    echo -e "${GREEN}✓ Cleanup completed${NC}"
fi

# Step 1: Create the shared Docker network
display_step 1 "Creating shared Docker network"
if docker network ls | grep -q $NETWORK_NAME; then
    echo -e "${GREEN}✓ Network $NETWORK_NAME already exists${NC}"
else
    echo -e "${YELLOW}Creating network $NETWORK_NAME...${NC}"
    docker network create $NETWORK_NAME
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Network $NETWORK_NAME created successfully${NC}"
    else
        echo -e "${RED}✗ Failed to create network $NETWORK_NAME${NC}"
        exit 1
    fi
fi

# Step 2: Start AWS services
display_step 2 "Starting AWS services"
if is_container_running "aws-s3" && is_container_running "aws-dynamodb"; then
    echo -e "${GREEN}✓ AWS services are already running${NC}"
else
    echo -e "${YELLOW}Starting AWS services...${NC}"
    cd $PROJECT_ROOT/deployment/aws
    docker compose up -d

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ AWS services started successfully${NC}"
    else
        echo -e "${RED}✗ Failed to start AWS services${NC}"
        exit 1
    fi

    # Wait for AWS services to be ready
    wait_for_container "aws-s3" 60
    wait_for_container "aws-dynamodb" 60

    # Wait for initialization
    echo -e "${YELLOW}Waiting for AWS services to initialize (10 seconds)...${NC}"
    sleep 10
fi

# Step 3: Start backend services
display_step 3 "Starting backend services"
if is_container_running "files-service" && is_container_running "sync-service"; then
    echo -e "${GREEN}✓ Backend services are already running${NC}"
else
    echo -e "${YELLOW}Starting backend services...${NC}"
    cd $PROJECT_ROOT/deployment/backend
    docker compose up -d

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Backend services started successfully${NC}"
    else
        echo -e "${RED}✗ Failed to start backend services${NC}"
        exit 1
    fi

    # Wait for backend services to be ready
    wait_for_container "files-service" 60
    wait_for_container "sync-service" 60

    # Wait for initialization
    echo -e "${YELLOW}Waiting for backend services to initialize (5 seconds)...${NC}"
    sleep 5
fi

# Step 4: Start client containers (Device A and Device B)
display_step 4 "Starting client containers"
if is_container_running "dropbox-client-a" && is_container_running "dropbox-client-b"; then
    echo -e "${GREEN}✓ Client containers are already running${NC}"
else
    echo -e "${YELLOW}Starting client containers (Device A and Device B)...${NC}"
    cd $PROJECT_ROOT/deployment/client
    docker compose -f docker-compose-multi.yml up -d

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Client containers started successfully${NC}"
    else
        echo -e "${RED}✗ Failed to start client containers${NC}"
        exit 1
    fi

    # Wait for client containers to be ready
    wait_for_container "dropbox-client-a" 60
    wait_for_container "dropbox-client-b" 60
fi

# Step 5: Verify all services are running
display_step 5 "Verifying all services"
echo -e "${YELLOW}Checking all containers...${NC}"

all_running=true
for container in "aws-s3" "aws-dynamodb" "files-service" "sync-service" "dropbox-client-a" "dropbox-client-b"; do
    if is_container_running $container; then
        echo -e "${GREEN}✓ $container is running${NC}"
    else
        echo -e "${RED}✗ $container is not running${NC}"
        all_running=false
    fi
done

if [ "$all_running" = true ]; then
    echo -e "\n${GREEN}All containers are running successfully!${NC}"

    # Display service URLs
    echo -e "\n${CYAN}Service URLs:${NC}"
    echo -e "  - Client APIs:"
    echo -e "    - Device A: ${GREEN}http://localhost:8000${NC}"
    echo -e "    - Device B: ${GREEN}http://localhost:8010${NC}"
    echo -e "  - Files Service API: ${GREEN}http://localhost:8001${NC}"
    echo -e "  - Sync Service API: ${GREEN}http://localhost:8003${NC}"
    echo -e "  - MinIO Console: ${GREEN}http://localhost:9001${NC}"
    echo -e "    Username: minioadmin"
    echo -e "    Password: minioadmin"
    echo -e "  - S3 API: ${GREEN}http://localhost:9000${NC}"
    echo -e "  - DynamoDB API: ${GREEN}http://localhost:8003${NC}"

    echo -e "\n${CYAN}To run tests:${NC}"
    echo -e "  ${GREEN}./client/tests/smoke/run_all_tests.sh${NC}"
else
    echo -e "\n${RED}Some containers failed to start. Please check the logs.${NC}"
    exit 1
fi

echo -e "${BLUE}=========================================${NC}"
exit 0