# End-to-End Tests for Dropbox Client

This directory contains end-to-end tests for the Dropbox client. These tests verify the functionality of the client in a real-world scenario, including file uploads, downloads, and synchronization between devices.

## Available Tests

### 1. File Upload Test (`test_file_upload.sh`)

Tests the basic file upload functionality of a single client:

- Creates a random file of specified size
- Copies it to the client's sync directory
- Verifies the file is processed and chunked correctly
- Checks database entries for the file and its chunks

Usage:
```bash
./client/tests/e2e/test_file_upload.sh [file_size_kb]
```

Example:
```bash
# Upload a 100KB file (default)
./client/tests/e2e/test_file_upload.sh

# Upload a 1MB file
./client/tests/e2e/test_file_upload.sh 1024
```

### 2. Device A Upload Test (`test_device_a_upload.sh`)

Tests that Device A can successfully upload a file to S3:

- Creates a small text file with unique content
- Copies it to Device A's sync directory
- Verifies the file is processed and uploaded to S3
- Checks database entries for the file and its chunks

Usage:
```bash
./client/tests/e2e/test_device_a_upload.sh
```

### 3. Device B Download Test (`test_device_b_download.sh`)

Tests that Device B can successfully download and sync a file that was uploaded by Device A:

- Finds the most recent test file in Device A
- Forces sync on Device B to download the file
- Verifies the file appears in Device B's sync directory
- Checks content integrity with MD5 hash comparison

Usage:
```bash
./client/tests/e2e/test_device_b_download.sh
```

Note: Run `test_device_a_upload.sh` first to ensure there's a file for Device B to download.

### 4. S3 Upload Test (`test_s3_upload.sh`)

Tests that Device A can successfully upload a file to S3:

- Creates a file with unique content on Device A
- Device A uploads the file to S3
- Verifies the upload was successful through logs and database entries

Usage:
```bash
./client/tests/e2e/test_s3_upload.sh
```

This test verifies the upload part of the synchronization process, which is currently working correctly.

### 5. S3 Sync Test (`test_s3_sync.sh`)

Tests the complete synchronization flow through S3:

- Creates a file with unique content on Device A
- Device A uploads the file to S3
- Device B polls and downloads the file from S3
- Verifies content integrity with MD5 hash comparison

Usage:
```bash
./client/tests/e2e/test_s3_sync.sh
```

Note: This test may fail due to a bug in the sync process on Device B. The error "object of type 'NoneType' has no len()" appears in the logs.

### 6. Multi-Device Synchronization Test (`test_multi_device_sync.sh`)

Tests file synchronization between Device A and Device B:

- Creates a file with unique content on Device A
- Waits for Device A to upload the file to the server
- Forces sync on Device B to download the file
- Verifies the file exists on Device B with identical content

Usage:
```bash
./client/tests/e2e/test_multi_device_sync.sh [file_size_kb]
```

Example:
```bash
# Sync a 100KB file (default)
./client/tests/e2e/test_multi_device_sync.sh

# Sync a 1MB file
./client/tests/e2e/test_multi_device_sync.sh 1024
```

Note: This test may fail due to the same bug in the sync process on Device B. Use `test_s3_upload.sh` to verify that at least the upload part works correctly.

## Prerequisites

Before running these tests:

1. Make sure Docker is running
2. Start the required containers:
   ```bash
   # For single-client tests
   ./client/scripts/bash/start_client_container.sh

   # For multi-device tests
   ./client/scripts/bash/start_multi_clients.sh
   ```

## Troubleshooting

If tests fail, check the following:

1. **Container Status**
   ```bash
   docker ps | grep dropbox-client
   ```

2. **Container Logs**
   ```bash
   # For single client
   docker logs dropbox-client

   # For multi-device setup
   docker logs dropbox-client-a
   docker logs dropbox-client-b
   ```

3. **Sync Directory Contents**
   ```bash
   # For single client
   docker exec dropbox-client ls -la /app/my_dropbox

   # For multi-device setup
   docker exec dropbox-client-a ls -la /app/my_dropbox
   docker exec dropbox-client-b ls -la /app/my_dropbox
   ```

4. **Database Status**
   ```bash
   # For single client
   docker exec dropbox-client sqlite3 /app/data/dropbox.db "SELECT * FROM files_metadata;"

   # For multi-device setup
   docker exec dropbox-client-a sqlite3 /app/data/dropbox.db "SELECT * FROM files_metadata;"
   docker exec dropbox-client-b sqlite3 /app/data/dropbox.db "SELECT * FROM files_metadata;"
   ```
