#!/bin/bash
#===================================================================================
# Dropbox S3 Sync Test
#===================================================================================
# Description: This script tests the complete synchronization flow:
# 1. Device A uploads a file to S3
# 2. Device B polls and downloads the file from S3
# 3. Verify content integrity between devices
#
# The test verifies the end-to-end synchronization process through S3.
#===================================================================================

# Set text colors for better readability
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Define constants
DEVICE_A_NAME="dropbox-client-a"
DEVICE_B_NAME="dropbox-client-b"
SYNC_DIR="/app/my_dropbox"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILE_NAME="s3_sync_test_${TIMESTAMP}.txt"
MAX_WAIT_TIME=120  # Maximum time to wait for sync (in seconds)

echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}Dropbox S3 Sync Test${NC}"
echo -e "${BLUE}=========================================${NC}"

# Check if both containers are running
echo -e "${YELLOW}Checking if both client containers are running...${NC}"
if ! docker ps | grep -q $DEVICE_A_NAME; then
    echo -e "${RED}Error: $DEVICE_A_NAME container is not running${NC}"
    echo -e "Please start the containers first with: ./client/scripts/bash/start_multi_clients.sh"
    exit 1
fi

if ! docker ps | grep -q $DEVICE_B_NAME; then
    echo -e "${RED}Error: $DEVICE_B_NAME container is not running${NC}"
    echo -e "Please start the containers first with: ./client/scripts/bash/start_multi_clients.sh"
    exit 1
fi

echo -e "${GREEN}Both client containers are running.${NC}"

# Step 1: Create a test file with unique content on Device A
echo -e "\n${YELLOW}Step 1: Creating a test file with unique content on Device A...${NC}"
UNIQUE_MARKER="S3_SYNC_TEST_MARKER_${TIMESTAMP}"
TEST_CONTENT="This is a test file for S3 synchronization.
It contains a unique marker: $UNIQUE_MARKER
This file was created at: $(date)
It should be synchronized from Device A to Device B through S3.
"

# Create the file directly in Device A's sync directory
echo -e "${YELLOW}Creating file directly in Device A's sync directory...${NC}"
docker exec $DEVICE_A_NAME bash -c "echo '$TEST_CONTENT' > $SYNC_DIR/$FILE_NAME"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Successfully created file in Device A: $SYNC_DIR/$FILE_NAME${NC}"
    echo -e "${CYAN}File contains unique marker: $UNIQUE_MARKER${NC}"
else
    echo -e "${RED}Failed to create file in Device A${NC}"
    exit 1
fi

# Step 2: Verify the file exists in Device A
echo -e "\n${YELLOW}Step 2: Verifying file exists in Device A...${NC}"
if docker exec $DEVICE_A_NAME ls -la $SYNC_DIR/$FILE_NAME >/dev/null 2>&1; then
    FILE_SIZE_A=$(docker exec $DEVICE_A_NAME du -h $SYNC_DIR/$FILE_NAME | cut -f1)
    echo -e "${GREEN}File exists in Device A: $SYNC_DIR/$FILE_NAME (${FILE_SIZE_A})${NC}"
    echo -e "${CYAN}File content in Device A:${NC}"
    docker exec $DEVICE_A_NAME cat $SYNC_DIR/$FILE_NAME
else
    echo -e "${RED}File not found in Device A${NC}"
    exit 1
fi

# Step 3: Calculate MD5 hash of the file in Device A
echo -e "\n${YELLOW}Step 3: Calculating MD5 hash of the file in Device A...${NC}"
DEVICE_A_MD5=$(docker exec $DEVICE_A_NAME md5sum $SYNC_DIR/$FILE_NAME | awk '{print $1}')
echo -e "${CYAN}Device A MD5 hash: $DEVICE_A_MD5${NC}"

# Step 4: Force sync on Device A to upload the file to S3
echo -e "\n${YELLOW}Step 4: Forcing sync on Device A to upload file to S3...${NC}"
SYNC_RESULT=$(docker exec $DEVICE_A_NAME curl -s -X POST http://localhost:8000/api/sync)
echo -e "${CYAN}Sync result: $SYNC_RESULT${NC}"

# Step 5: Wait for file to be processed and uploaded to S3
echo -e "\n${YELLOW}Step 5: Waiting for file to be processed and uploaded to S3...${NC}"
echo -e "${CYAN}Checking logs for upload confirmation...${NC}"

start_time=$(date +%s)
end_time=$((start_time + 30))  # Wait up to 30 seconds for upload
upload_success=false

while [ $(date +%s) -lt $end_time ] && [ "$upload_success" = false ]; do
    # Check logs for upload confirmation
    UPLOAD_LOG=$(docker logs --tail 50 $DEVICE_A_NAME 2>&1 | grep -E "Uploaded file.*$FILE_NAME")
    
    if [ -n "$UPLOAD_LOG" ]; then
        upload_success=true
        elapsed=$(($(date +%s) - start_time))
        echo -e "${GREEN}File successfully uploaded after ${elapsed} seconds!${NC}"
        echo -e "${CYAN}Upload confirmation: $UPLOAD_LOG${NC}"
        break
    else
        echo -e "${YELLOW}File upload not yet confirmed. Waiting...${NC}"
    fi
    
    # Wait before checking again
    sleep 5
done

if [ "$upload_success" = false ]; then
    echo -e "${RED}Failed to confirm file upload within 30 seconds${NC}"
    echo -e "${YELLOW}Last 20 log lines from Device A:${NC}"
    docker logs --tail 20 $DEVICE_A_NAME
    exit 1
fi

# Step 6: Check if the file is in Device A's database
echo -e "\n${YELLOW}Step 6: Checking if file is in Device A's database...${NC}"
DB_RESULT=$(docker exec $DEVICE_A_NAME sqlite3 /app/data/dropbox.db "SELECT file_id, file_path, file_name FROM files_metadata WHERE file_name = '$FILE_NAME'")

if [ -n "$DB_RESULT" ]; then
    echo -e "${GREEN}File found in Device A's database: $DB_RESULT${NC}"
    # Extract file_id for reference
    FILE_ID=$(echo "$DB_RESULT" | cut -d'|' -f1)
    echo -e "${CYAN}File ID: $FILE_ID${NC}"
else
    echo -e "${RED}File not found in Device A's database${NC}"
    exit 1
fi

# Step 7: Force sync on Device B to download the file from S3
echo -e "\n${YELLOW}Step 7: Forcing sync on Device B to download file from S3...${NC}"
SYNC_RESULT=$(docker exec $DEVICE_B_NAME curl -s -X POST http://localhost:8000/api/sync)
echo -e "${CYAN}Sync result: $SYNC_RESULT${NC}"

# Step 8: Wait for the file to appear in Device B
echo -e "\n${YELLOW}Step 8: Waiting for file to appear in Device B...${NC}"
echo -e "${CYAN}Checking every 5 seconds for up to ${MAX_WAIT_TIME} seconds...${NC}"

start_time=$(date +%s)
end_time=$((start_time + MAX_WAIT_TIME))
sync_success=false

while [ $(date +%s) -lt $end_time ] && [ "$sync_success" = false ]; do
    # Force sync on Device B again
    docker exec $DEVICE_B_NAME curl -s -X POST http://localhost:8000/api/sync > /dev/null
    
    # Check if file exists in Device B
    if docker exec $DEVICE_B_NAME ls -la $SYNC_DIR/$FILE_NAME >/dev/null 2>&1; then
        sync_success=true
        elapsed=$(($(date +%s) - start_time))
        echo -e "${GREEN}File appeared in Device B after ${elapsed} seconds!${NC}"
        break
    else
        echo -e "${YELLOW}File not yet in Device B. Waiting...${NC}"
    fi
    
    # Wait before checking again
    sleep 5
done

if [ "$sync_success" = false ]; then
    echo -e "${RED}Failed to sync file to Device B within ${MAX_WAIT_TIME} seconds${NC}"
    echo -e "${YELLOW}Listing files in Device B's sync directory:${NC}"
    docker exec $DEVICE_B_NAME ls -la $SYNC_DIR
    echo -e "${YELLOW}Last 20 log lines from Device B:${NC}"
    docker logs --tail 20 $DEVICE_B_NAME
    
    # Check if the file is in Device B's database even if not in sync dir
    echo -e "${YELLOW}Checking if file is in Device B's database...${NC}"
    DB_RESULT_B=$(docker exec $DEVICE_B_NAME sqlite3 /app/data/dropbox.db "SELECT file_id, file_path, file_name FROM files_metadata WHERE file_name = '$FILE_NAME'")
    if [ -n "$DB_RESULT_B" ]; then
        echo -e "${CYAN}File found in Device B's database but not in sync directory: $DB_RESULT_B${NC}"
    else
        echo -e "${CYAN}File not found in Device B's database${NC}"
    fi
    
    exit 1
fi

# Step 9: Verify file content in Device B
echo -e "\n${YELLOW}Step 9: Verifying file content in Device B...${NC}"
if docker exec $DEVICE_B_NAME ls -la $SYNC_DIR/$FILE_NAME >/dev/null 2>&1; then
    FILE_SIZE_B=$(docker exec $DEVICE_B_NAME du -h $SYNC_DIR/$FILE_NAME | cut -f1)
    echo -e "${GREEN}File exists in Device B: $SYNC_DIR/$FILE_NAME (${FILE_SIZE_B})${NC}"
    echo -e "${CYAN}File content in Device B:${NC}"
    docker exec $DEVICE_B_NAME cat $SYNC_DIR/$FILE_NAME
else
    echo -e "${RED}File not found in Device B${NC}"
    exit 1
fi

# Step 10: Calculate MD5 hash of the file in Device B
echo -e "\n${YELLOW}Step 10: Calculating MD5 hash of the file in Device B...${NC}"
DEVICE_B_MD5=$(docker exec $DEVICE_B_NAME md5sum $SYNC_DIR/$FILE_NAME | awk '{print $1}')
echo -e "${CYAN}Device B MD5 hash: $DEVICE_B_MD5${NC}"

# Step 11: Compare MD5 hashes
echo -e "\n${YELLOW}Step 11: Comparing MD5 hashes...${NC}"
echo -e "${CYAN}Device A MD5: $DEVICE_A_MD5${NC}"
echo -e "${CYAN}Device B MD5: $DEVICE_B_MD5${NC}"

if [ "$DEVICE_A_MD5" = "$DEVICE_B_MD5" ]; then
    echo -e "${GREEN}File content matches between Device A and Device B - GOOD!${NC}"
else
    echo -e "${RED}File content does not match between devices!${NC}"
    exit 1
fi

# Step 12: Check if the file is in Device B's database
echo -e "\n${YELLOW}Step 12: Checking if file is in Device B's database...${NC}"
DB_RESULT_B=$(docker exec $DEVICE_B_NAME sqlite3 /app/data/dropbox.db "SELECT file_id, file_path, file_name FROM files_metadata WHERE file_name = '$FILE_NAME'")

if [ -n "$DB_RESULT_B" ]; then
    echo -e "${GREEN}File found in Device B's database: $DB_RESULT_B${NC}"
else
    echo -e "${RED}File not found in Device B's database${NC}"
    exit 1
fi

echo -e "\n${BLUE}=========================================${NC}"
echo -e "${GREEN}Test completed successfully!${NC}"
echo -e "${BLUE}=========================================${NC}"
echo -e "${CYAN}File synced through S3: $FILE_NAME${NC}"
echo -e "${CYAN}The file was successfully synced from Device A to Device B through S3${NC}"
echo -e "${CYAN}Content integrity verified with matching MD5 hashes${NC}"
echo -e "${BLUE}=========================================${NC}"

exit 0
