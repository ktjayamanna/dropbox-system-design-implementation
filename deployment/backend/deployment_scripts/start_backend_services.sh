#!/bin/bash

# Set text colors for better readability
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}Starting Dropbox Backend Services${NC}"
echo -e "${BLUE}=========================================${NC}"

# Check if AWS services are running
if ! docker ps | grep -q aws-api-gateway; then
    echo -e "${RED}Error: AWS services are not running${NC}"
    echo -e "Please start AWS services first with: ./deployment/aws/deployment_scripts/start_aws_services.sh"
    exit 1
fi

# Create network if it doesn't exist
if ! docker network ls | grep -q dropbox-network; then
    echo -e "${YELLOW}Creating dropbox-network...${NC}"
    docker network create dropbox-network

    # Connect AWS services to the network
    echo -e "${YELLOW}Connecting AWS services to dropbox-network...${NC}"
    docker network connect dropbox-network aws-api-gateway
    docker network connect dropbox-network aws-s3
    docker network connect dropbox-network aws-dynamodb
fi

# Navigate to the backend directory
cd "$(dirname "$0")/.." || {
    echo -e "${RED}Error: Could not navigate to the backend directory${NC}"
    exit 1
}

# Start the containers
echo -e "${YELLOW}Starting backend services...${NC}"
docker compose up -d

# Check if containers are running
if [ $? -eq 0 ]; then
    echo -e "${GREEN}Backend services started successfully!${NC}"
    echo -e "${YELLOW}Services available at:${NC}"
    echo -e "  - Files Service API: ${GREEN}http://localhost:8001/${NC}"
    echo -e "  - Sync Service API: ${GREEN}http://localhost:8003/${NC}"
else
    echo -e "${RED}Failed to start backend services. Check docker logs for details.${NC}"
    exit 1
fi

echo -e "${BLUE}=========================================${NC}"
