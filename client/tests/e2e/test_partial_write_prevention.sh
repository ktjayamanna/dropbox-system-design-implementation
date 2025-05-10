#!/bin/bash
#===================================================================================
# Dropbox Partial Write Prevention Test
#===================================================================================
# Description: This script tests the IN_MODIFY → IN_CLOSE_WRITE pattern implementation
# to prevent syncing partial writes:
# 1. Creates a file in Device A's sync folder
# 2. Makes multiple modifications to the file with small delays between them
# 3. Verifies that the file is only synced after it's closed
# 4. Checks logs to confirm our pattern is working
#
# The test verifies that the system doesn't sync partial writes.
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
TIMESTAMP=$(date +%s)
FILE_NAME="partial_write_test_${TIMESTAMP}.txt"
MAX_WAIT_TIME=60  # Maximum time to wait for sync in seconds

# Check if both client containers are running
echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}Dropbox Partial Write Prevention Test${NC}"
echo -e "${BLUE}=========================================${NC}"

echo -e "${YELLOW}Checking if client containers are running...${NC}"
if ! docker ps | grep -q $DEVICE_A_NAME; then
    echo -e "${RED}Error: $DEVICE_A_NAME container is not running${NC}"
    echo -e "Please start the containers first with: ./deployment/scripts/start_all.sh"
    exit 1
fi

if ! docker ps | grep -q $DEVICE_B_NAME; then
    echo -e "${RED}Error: $DEVICE_B_NAME container is not running${NC}"
    echo -e "Please start the containers first with: ./deployment/scripts/start_all.sh"
    exit 1
fi

echo -e "${GREEN}Both client containers are running.${NC}"

# Step 1: Create a test file with initial content on Device A
echo -e "\n${YELLOW}Step 1: Creating a test file with initial content on Device A...${NC}"
UNIQUE_MARKER="PARTIAL_WRITE_TEST_MARKER_${TIMESTAMP}"
INITIAL_CONTENT="This is the initial content of the test file.
It contains a unique marker: $UNIQUE_MARKER
This file was created at: $(date)
"

# Create the file directly in Device A's sync directory
echo -e "${YELLOW}Creating file directly in Device A's sync directory...${NC}"
docker exec $DEVICE_A_NAME bash -c "echo '$INITIAL_CONTENT' > $SYNC_DIR/$FILE_NAME"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Successfully created file in Device A: $SYNC_DIR/$FILE_NAME${NC}"
    echo -e "${CYAN}File contains unique marker: $UNIQUE_MARKER${NC}"
else
    echo -e "${RED}Failed to create file in Device A${NC}"
    exit 1
fi

# Step 2: Wait for the initial file to be processed
echo -e "\n${YELLOW}Step 2: Waiting for initial file to be processed (5 seconds)...${NC}"
sleep 5

# Step 3: Check logs to confirm the file was synced
echo -e "\n${YELLOW}Step 3: Checking logs to confirm initial file was synced...${NC}"
INITIAL_SYNC_LOG=$(docker logs --tail 50 $DEVICE_A_NAME 2>&1 | grep -E "Uploaded file.*$FILE_NAME")

if [ -n "$INITIAL_SYNC_LOG" ]; then
    echo -e "${GREEN}Initial file was synced:${NC}"
    echo -e "${CYAN}$INITIAL_SYNC_LOG${NC}"
else
    echo -e "${RED}Could not confirm initial file sync in logs${NC}"
    # Continue anyway as this might be due to log buffering
fi

# Step 4: Start a Python script to make multiple modifications to the file
echo -e "\n${YELLOW}Step 4: Making multiple modifications to the file...${NC}"

# Create a Python script to modify the file multiple times
PYTHON_SCRIPT=$(cat << 'EOF'
import sys
import time
import os

file_path = sys.argv[1]
marker = sys.argv[2]
iterations = 5

for i in range(iterations):
    # Open the file in append mode
    with open(file_path, 'a') as f:
        content = f"\nModification #{i+1} at {time.strftime('%H:%M:%S')}\n"
        content += f"This is a partial write that should not be synced until the file is closed.\n"
        f.write(content)
        # Flush but don't close to simulate a partial write
        f.flush()
        print(f"Added modification #{i+1} to {file_path}")
        # Sleep to allow the system to detect the modification
        time.sleep(2)

# Final modification with the completion marker
with open(file_path, 'a') as f:
    content = f"\nFINAL MODIFICATION at {time.strftime('%H:%M:%S')}\n"
    content += f"COMPLETION MARKER: {marker}\n"
    content += f"All modifications are complete. The file should now be synced.\n"
    f.write(content)
    print(f"Added final modification with completion marker to {file_path}")

print("All modifications complete")
EOF
)

# Save the Python script to a temporary file in the container
docker exec $DEVICE_A_NAME bash -c "cat > /tmp/modify_file.py << 'EOL'
$PYTHON_SCRIPT
EOL"

# Execute the Python script in the container
COMPLETION_MARKER="COMPLETION_${TIMESTAMP}"
echo -e "${CYAN}Running Python script to modify the file multiple times...${NC}"
docker exec $DEVICE_A_NAME python3 /tmp/modify_file.py "$SYNC_DIR/$FILE_NAME" "$COMPLETION_MARKER"

# Step 5: Check logs to see if our pattern is working
echo -e "\n${YELLOW}Step 5: Checking logs to confirm IN_MODIFY → IN_CLOSE_WRITE pattern...${NC}"
sleep 2  # Give some time for logs to be written

# Look for evidence of our pattern in the logs
MODIFY_LOGS=$(docker logs --tail 100 $DEVICE_A_NAME 2>&1 | grep -E "Marked file as modified.*$FILE_NAME")
CLOSE_WRITE_LOGS=$(docker logs --tail 100 $DEVICE_A_NAME 2>&1 | grep -E "File closed after write.*$FILE_NAME")
SKIPPED_SYNC_LOGS=$(docker logs --tail 100 $DEVICE_A_NAME 2>&1 | grep -E "Skipping sync for modified file.*$FILE_NAME")
FINAL_SYNC_LOGS=$(docker logs --tail 100 $DEVICE_A_NAME 2>&1 | grep -E "Uploaded file after close_write.*$FILE_NAME")

echo -e "${CYAN}Found evidence of IN_MODIFY events:${NC}"
if [ -n "$MODIFY_LOGS" ]; then
    echo -e "${GREEN}$MODIFY_LOGS${NC}"
else
    echo -e "${RED}No IN_MODIFY events found in logs${NC}"
fi

echo -e "${CYAN}Found evidence of skipped syncs during modification:${NC}"
if [ -n "$SKIPPED_SYNC_LOGS" ]; then
    echo -e "${GREEN}$SKIPPED_SYNC_LOGS${NC}"
else
    echo -e "${RED}No skipped syncs found in logs${NC}"
fi

echo -e "${CYAN}Found evidence of IN_CLOSE_WRITE events:${NC}"
if [ -n "$CLOSE_WRITE_LOGS" ]; then
    echo -e "${GREEN}$CLOSE_WRITE_LOGS${NC}"
else
    echo -e "${RED}No IN_CLOSE_WRITE events found in logs${NC}"
fi

echo -e "${CYAN}Found evidence of final sync after close:${NC}"
if [ -n "$FINAL_SYNC_LOGS" ]; then
    echo -e "${GREEN}$FINAL_SYNC_LOGS${NC}"
else
    echo -e "${RED}No final sync after close found in logs${NC}"
fi

# Step 6: Force sync on Device B to get the file
echo -e "\n${YELLOW}Step 6: Forcing sync on Device B to get the file...${NC}"
SYNC_RESULT=$(docker exec $DEVICE_B_NAME curl -s -X POST http://localhost:8000/api/sync)
echo -e "${CYAN}Sync result: $SYNC_RESULT${NC}"

# Step 7: Wait for the file to appear in Device B
echo -e "\n${YELLOW}Step 7: Waiting for file to appear in Device B...${NC}"
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
    echo -e "${RED}File did not appear in Device B within the timeout period${NC}"
    exit 1
fi

# Step 8: Verify the file in Device B has the completion marker
echo -e "\n${YELLOW}Step 8: Verifying file in Device B has the completion marker...${NC}"
if docker exec $DEVICE_B_NAME grep -q "$COMPLETION_MARKER" "$SYNC_DIR/$FILE_NAME"; then
    echo -e "${GREEN}File in Device B contains the completion marker!${NC}"
    echo -e "${CYAN}File content in Device B:${NC}"
    docker exec $DEVICE_B_NAME cat $SYNC_DIR/$FILE_NAME
else
    echo -e "${RED}File in Device B does not contain the completion marker${NC}"
    echo -e "${CYAN}Current file content in Device B:${NC}"
    docker exec $DEVICE_B_NAME cat $SYNC_DIR/$FILE_NAME
    exit 1
fi

# Step 9: Final verification
echo -e "\n${YELLOW}Step 9: Final verification...${NC}"

# Count the number of modifications in the file
MOD_COUNT_A=$(docker exec $DEVICE_A_NAME grep -c "Modification #" "$SYNC_DIR/$FILE_NAME")
MOD_COUNT_B=$(docker exec $DEVICE_B_NAME grep -c "Modification #" "$SYNC_DIR/$FILE_NAME")

echo -e "${CYAN}Number of modifications in Device A: $MOD_COUNT_A${NC}"
echo -e "${CYAN}Number of modifications in Device B: $MOD_COUNT_B${NC}"

if [ "$MOD_COUNT_A" = "$MOD_COUNT_B" ]; then
    echo -e "${GREEN}All modifications were successfully synced!${NC}"
else
    echo -e "${RED}Not all modifications were synced correctly${NC}"
    exit 1
fi

echo -e "\n${GREEN}Partial Write Prevention Test PASSED!${NC}"
echo -e "${BLUE}=========================================${NC}"
