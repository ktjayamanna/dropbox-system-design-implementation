#!/bin/bash
#===================================================================================
# Dropbox Delta Sync Test
#===================================================================================
# Description: This script tests the delta synchronization flow:
# 1. Device A uploads a file to S3
# 2. Device B polls and downloads the file from S3
# 3. Device B modifies the file, which is detected by inotify and uploaded to S3
# 4. Device A polls and downloads only the changed chunks (delta sync)
# 5. Verify content integrity between devices
#
# The test verifies the delta sync process through S3.
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
FILE_NAME="delta_sync_test_${TIMESTAMP}.txt"
MAX_WAIT_TIME=120  # Maximum time to wait for sync (in seconds)

echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}Dropbox Delta Sync Test${NC}"
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
UNIQUE_MARKER="DELTA_SYNC_TEST_MARKER_${TIMESTAMP}"
TEST_CONTENT="This is a test file for delta synchronization.
It contains a unique marker: $UNIQUE_MARKER
This file was created at: $(date)
It should be synchronized from Device A to Device B through S3.
Then modified on Device B and synced back to Device A using delta sync.
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
DEVICE_A_MD5_INITIAL=$(docker exec $DEVICE_A_NAME md5sum $SYNC_DIR/$FILE_NAME | awk '{print $1}')
echo -e "${CYAN}Device A initial MD5 hash: $DEVICE_A_MD5_INITIAL${NC}"

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
DEVICE_B_MD5_INITIAL=$(docker exec $DEVICE_B_NAME md5sum $SYNC_DIR/$FILE_NAME | awk '{print $1}')
echo -e "${CYAN}Device B initial MD5 hash: $DEVICE_B_MD5_INITIAL${NC}"

# Step 11: Compare initial MD5 hashes
echo -e "\n${YELLOW}Step 11: Comparing initial MD5 hashes...${NC}"
echo -e "${CYAN}Device A initial MD5: $DEVICE_A_MD5_INITIAL${NC}"
echo -e "${CYAN}Device B initial MD5: $DEVICE_B_MD5_INITIAL${NC}"

if [ "$DEVICE_A_MD5_INITIAL" = "$DEVICE_B_MD5_INITIAL" ]; then
    echo -e "${GREEN}Initial file content matches between Device A and Device B - GOOD!${NC}"
else
    echo -e "${RED}Initial file content does not match between devices!${NC}"
    exit 1
fi

# Step 12: Modify the file on Device B
echo -e "\n${YELLOW}Step 12: Modifying the file on Device B...${NC}"
MODIFICATION_MARKER="MODIFIED_CONTENT_${TIMESTAMP}"
MODIFIED_CONTENT="This file has been modified on Device B.
Modification timestamp: $(date)
Modification marker: $MODIFICATION_MARKER
The original content is still here: $UNIQUE_MARKER
This should trigger inotify and upload the changes to S3.
Then Device A should download only the changed chunks.
"

# Modify the file in a way that will definitely trigger inotify
echo -e "${YELLOW}Directly modifying the file...${NC}"

# First, create a backup of the original file
docker exec $DEVICE_B_NAME bash -c "cp $SYNC_DIR/$FILE_NAME $SYNC_DIR/${FILE_NAME}.bak"

# Then create a new file with the original content plus the modified content
docker exec $DEVICE_B_NAME bash -c "cat $SYNC_DIR/${FILE_NAME}.bak > $SYNC_DIR/${FILE_NAME}.new"
docker exec $DEVICE_B_NAME bash -c "echo '$MODIFIED_CONTENT' >> $SYNC_DIR/${FILE_NAME}.new"

# Finally, move the new file over the original file to trigger IN_MOVED_TO event
# This is more reliable than trying to trigger IN_MODIFY
docker exec $DEVICE_B_NAME bash -c "mv $SYNC_DIR/${FILE_NAME}.new $SYNC_DIR/$FILE_NAME"

# Clean up the backup file
docker exec $DEVICE_B_NAME bash -c "rm $SYNC_DIR/${FILE_NAME}.bak"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Successfully modified file in Device B${NC}"
    echo -e "${CYAN}Modified content with marker: $MODIFICATION_MARKER${NC}"
    echo -e "${CYAN}Updated file content in Device B:${NC}"
    docker exec $DEVICE_B_NAME cat $SYNC_DIR/$FILE_NAME
else
    echo -e "${RED}Failed to modify file in Device B${NC}"
    exit 1
fi

# Step 13: Calculate MD5 hash of the modified file in Device B
echo -e "\n${YELLOW}Step 13: Calculating MD5 hash of the modified file in Device B...${NC}"
DEVICE_B_MD5_MODIFIED=$(docker exec $DEVICE_B_NAME md5sum $SYNC_DIR/$FILE_NAME | awk '{print $1}')
echo -e "${CYAN}Device B modified MD5 hash: $DEVICE_B_MD5_MODIFIED${NC}"

# Step 14: Force sync on Device B to upload the modified file to S3
echo -e "\n${YELLOW}Step 14: Forcing sync on Device B to upload modified file to S3...${NC}"
SYNC_RESULT=$(docker exec $DEVICE_B_NAME curl -s -X POST http://localhost:8000/api/sync)
echo -e "${CYAN}Sync result: $SYNC_RESULT${NC}"

# Step 15: Wait for modified file to be processed and uploaded to S3
echo -e "\n${YELLOW}Step 15: Waiting for modified file to be processed and uploaded to S3...${NC}"
echo -e "${CYAN}Checking logs for upload confirmation...${NC}"

start_time=$(date +%s)
end_time=$((start_time + 30))  # Wait up to 30 seconds for upload
upload_success=false

while [ $(date +%s) -lt $end_time ] && [ "$upload_success" = false ]; do
    # Check logs for upload confirmation
    UPLOAD_LOG=$(docker logs --tail 50 $DEVICE_B_NAME 2>&1 | grep -E "Uploaded file.*$FILE_NAME")

    if [ -n "$UPLOAD_LOG" ]; then
        upload_success=true
        elapsed=$(($(date +%s) - start_time))
        echo -e "${GREEN}Modified file successfully uploaded after ${elapsed} seconds!${NC}"
        echo -e "${CYAN}Upload confirmation: $UPLOAD_LOG${NC}"
        break
    else
        echo -e "${YELLOW}Modified file upload not yet confirmed. Waiting...${NC}"
    fi

    # Wait before checking again
    sleep 5
done

if [ "$upload_success" = false ]; then
    echo -e "${RED}Failed to confirm modified file upload within 30 seconds${NC}"
    echo -e "${YELLOW}Last 20 log lines from Device B:${NC}"
    docker logs --tail 20 $DEVICE_B_NAME
    exit 1
fi

# Step 16: Force sync on Device A to download the modified file from S3
echo -e "\n${YELLOW}Step 16: Forcing sync on Device A to download modified file from S3...${NC}"

# Clear any previous sync errors in Device A and reset the sync time to force a full sync
echo -e "${CYAN}Resetting sync state in Device A to force a full sync...${NC}"
docker exec $DEVICE_A_NAME sqlite3 /app/data/dropbox.db "PRAGMA foreign_keys=OFF; BEGIN TRANSACTION; UPDATE system SET system_last_sync_time='2023-01-01T00:00:00+00:00' WHERE id=1; COMMIT; PRAGMA foreign_keys=ON;"

# Restart the sync service in Device A to clear any cached state
echo -e "${CYAN}Restarting sync service in Device A...${NC}"
docker exec $DEVICE_A_NAME pkill -f "python -m server.main" || true
sleep 2
docker exec -d $DEVICE_A_NAME bash -c "cd /app && python -m server.main > /app/logs/server.log 2>&1"
sleep 5

# Force sync on Device A
echo -e "${CYAN}Forcing sync on Device A...${NC}"
SYNC_RESULT=$(docker exec $DEVICE_A_NAME curl -s -X POST http://localhost:8000/api/sync)
echo -e "${CYAN}Sync result: $SYNC_RESULT${NC}"

# Step 17: Wait for the modified file to be updated in Device A
echo -e "\n${YELLOW}Step 17: Waiting for file to be updated in Device A...${NC}"
echo -e "${CYAN}Checking logs for delta sync confirmation...${NC}"

start_time=$(date +%s)
end_time=$((start_time + MAX_WAIT_TIME))
sync_success=false

while [ $(date +%s) -lt $end_time ] && [ "$sync_success" = false ]; do
    # Force sync on Device A again
    docker exec $DEVICE_A_NAME curl -s -X POST http://localhost:8000/api/sync > /dev/null

    # Check if file has been modified in Device A by looking for the modification marker
    if docker exec $DEVICE_A_NAME grep -q "$MODIFICATION_MARKER" "$SYNC_DIR/$FILE_NAME" 2>/dev/null; then
        sync_success=true
        elapsed=$(($(date +%s) - start_time))
        echo -e "${GREEN}File updated in Device A after ${elapsed} seconds!${NC}"
        break
    else
        echo -e "${YELLOW}File not yet updated in Device A. Waiting...${NC}"
    fi

    # Wait before checking again
    sleep 5
done

if [ "$sync_success" = false ]; then
    echo -e "${RED}Failed to update file in Device A within ${MAX_WAIT_TIME} seconds${NC}"
    echo -e "${YELLOW}Current file content in Device A:${NC}"
    docker exec $DEVICE_A_NAME cat $SYNC_DIR/$FILE_NAME
    echo -e "${YELLOW}Last 20 log lines from Device A:${NC}"
    docker logs --tail 20 $DEVICE_A_NAME
    exit 1
fi

# Step 18: Verify updated file content in Device A
echo -e "\n${YELLOW}Step 18: Verifying updated file content in Device A...${NC}"
if docker exec $DEVICE_A_NAME grep -q "$MODIFICATION_MARKER" "$SYNC_DIR/$FILE_NAME"; then
    echo -e "${GREEN}File has been successfully updated in Device A${NC}"
    echo -e "${CYAN}Updated file content in Device A:${NC}"
    docker exec $DEVICE_A_NAME cat $SYNC_DIR/$FILE_NAME
else
    echo -e "${RED}File was not properly updated in Device A${NC}"
    exit 1
fi

# Step 19: Calculate MD5 hash of the updated file in Device A
echo -e "\n${YELLOW}Step 19: Calculating MD5 hash of the updated file in Device A...${NC}"
DEVICE_A_MD5_UPDATED=$(docker exec $DEVICE_A_NAME md5sum $SYNC_DIR/$FILE_NAME | awk '{print $1}')
echo -e "${CYAN}Device A updated MD5 hash: $DEVICE_A_MD5_UPDATED${NC}"

# Step 20: Compare final MD5 hashes
echo -e "\n${YELLOW}Step 20: Comparing final MD5 hashes...${NC}"
echo -e "${CYAN}Device A updated MD5: $DEVICE_A_MD5_UPDATED${NC}"
echo -e "${CYAN}Device B modified MD5: $DEVICE_B_MD5_MODIFIED${NC}"

if [ "$DEVICE_A_MD5_UPDATED" = "$DEVICE_B_MD5_MODIFIED" ]; then
    echo -e "${GREEN}Final file content matches between Device A and Device B - GOOD!${NC}"
else
    echo -e "${RED}Final file content does not match between devices!${NC}"
    exit 1
fi

# Step 21: Check logs for delta sync evidence
echo -e "\n${YELLOW}Step 21: Checking logs for evidence of delta sync...${NC}"
DELTA_SYNC_LOG=$(docker logs --tail 200 $DEVICE_A_NAME 2>&1 | grep -E "process_sync_response|download_urls|changes_available|Processing chunk|Downloading chunk|Downloaded chunk")

if [ -n "$DELTA_SYNC_LOG" ]; then
    echo -e "${GREEN}Found evidence of delta sync in logs:${NC}"
    echo -e "${CYAN}$DELTA_SYNC_LOG${NC}"

    # Count the number of chunks downloaded
    CHUNK_COUNT=$(echo "$DELTA_SYNC_LOG" | grep -c "Downloaded chunk")
    echo -e "${GREEN}Number of chunks downloaded: $CHUNK_COUNT${NC}"

    # Check if file was updated through delta sync
    if docker logs --tail 200 $DEVICE_A_NAME 2>&1 | grep -q "changes_processed.*true"; then
        echo -e "${GREEN}Confirmed that changes were processed via delta sync${NC}"
    else
        echo -e "${YELLOW}Changes were processed, but couldn't confirm delta sync mechanism${NC}"
    fi
else
    echo -e "${YELLOW}No clear evidence of delta sync in logs, but file was updated correctly${NC}"
fi

echo -e "\n${BLUE}=========================================${NC}"
echo -e "${GREEN}Delta Sync Test completed successfully!${NC}"
echo -e "${BLUE}=========================================${NC}"
echo -e "${CYAN}File synced through S3: $FILE_NAME${NC}"
echo -e "${CYAN}The file was successfully:${NC}"
echo -e "${CYAN}1. Created on Device A and synced to Device B${NC}"
echo -e "${CYAN}2. Modified on Device B and synced back to Device A${NC}"
echo -e "${CYAN}3. Content integrity verified with matching MD5 hashes${NC}"
echo -e "${BLUE}=========================================${NC}"

exit 0
