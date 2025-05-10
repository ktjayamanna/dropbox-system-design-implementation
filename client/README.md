# Dropbox Client

This is the client component of the Dropbox-like system. It provides a local synchronization service with the following features:

- File synchronization using inotify for real-time change detection
- File chunking (5MB chunks) for efficient synchronization
- SQLite database for storing file metadata and chunk information
- FastAPI server for API access

## Directory Structure

```
client/
├── alembic/            # Database migration scripts
├── db/                 # SQLite database models and connection
│   ├── engine.py       # SQLAlchemy engine and session setup
│   ├── __init__.py
│   └── models.py       # Database models
├── scripts/            # Utility scripts
│   ├── bash/           # Bash scripts for various operations
│   ├── sql/            # SQL scripts for database operations
│   └── python/         # Python utility scripts
├── server/             # FastAPI server and sync logic
│   ├── api.py          # API routes
│   ├── chunker.py      # File chunking logic
│   ├── main.py         # FastAPI application
│   ├── sync.py         # Synchronization engine
│   └── watcher.py      # inotify integration
├── tests/              # Test suite
│   ├── mock_data/      # Mock data for testing
│   ├── smoke/          # Smoke tests
│   └── README.md       # Test documentation
├── alembic.ini         # Alembic configuration
├── config.py           # Application configuration
└── requirements.txt    # Python dependencies
```

## Database Models

### FilesMetaData
- file_id: Primary key, unique identifier for the file
- folder_id: Identifier for the parent folder
- file_type: Type of the file

### Chunks
- chunk_id: Primary key, unique identifier for the chunk
- file_id: Foreign key to FilesMetaData
- created_at: Timestamp when the chunk was created
- last_synced: Timestamp when the chunk was last synchronized
- fingerprint: Hash of the chunk data for integrity verification

## Running the Client

The client is designed to run in a Docker container. There are two ways to run the client:

### Single Client (Device A)

Use the following command to start a single client instance:

```bash
./client/scripts/bash/start_client_container.sh
```

This will start the Device A client container with the FastAPI server running on port 8000.

### Multi-Client Setup (Device A and Device B)

To run two client instances simultaneously (for testing synchronization between devices):

```bash
./client/scripts/bash/start_multi_clients.sh
```

This will start:
- Device A: accessible at http://localhost:8000
- Device B: accessible at http://localhost:8010

For more information about the multi-client setup, see [client/docs/multi_client_setup.md](docs/multi_client_setup.md).

## Testing the Client

The client includes a comprehensive test suite to verify its functionality:

### Smoke Tests

The smoke tests are located in the `client/tests/smoke` directory and can be run individually or all at once:

```bash
# Run all smoke tests
./client/tests/smoke/run_all_tests.sh

# Run specific tests
./client/tests/smoke/test_file_sync.sh
./client/tests/smoke/test_file_modifications.sh
./client/tests/smoke/test_folder_operations.sh
./client/tests/smoke/test_api_endpoints.sh
```

The test suite includes:

1. **File Synchronization Test** (`test_file_sync.sh`)
   - Tests basic file upload and synchronization
   - Verifies files are properly tracked in the database
   - Checks folder creation and tracking

2. **File Modifications Test** (`test_file_modifications.sh`)
   - Tests file content modification detection
   - Verifies hash changes are detected and recorded
   - Checks chunk recreation on file modification

3. **Folder Operations Test** (`test_folder_operations.sh`)
   - Tests nested folder structure creation
   - Verifies parent-child folder relationships
   - Checks file creation in nested folders

4. **API Endpoints Test** (`test_api_endpoints.sh`)
   - Tests all API endpoints for proper functionality
   - Verifies file and folder metadata retrieval
   - Checks system health endpoints

For more information about the test suite, see [client/tests/README.md](tests/README.md).
