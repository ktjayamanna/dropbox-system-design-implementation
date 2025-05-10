# Sync Service

This microservice is responsible for handling file synchronization between clients and the server.

## Features

- Poll for changes since the last sync
- Return download URLs for updated chunks
- Provide file manifests for clients to reconstruct files

## API Endpoints

- `GET /health`: Health check endpoint
- `POST /poll`: Poll for changes since the last sync

## How It Works

1. Client sends a poll request with its last sync timestamp
2. Service queries DynamoDB for chunks updated after that timestamp
3. If no updated chunks, returns a "synced" status
4. If updated chunks exist:
   - Generates download URLs for the updated chunks
   - Creates file manifests for each affected file
   - Returns this information to the client
5. Client downloads the updated chunks and updates its local database

## Integration with Files Service

The Sync Service relies on the Files Service for:
- Accessing the shared DynamoDB tables (FilesMetaData, Chunks, Folders)
- Generating download URLs for chunks

## Configuration

The service can be configured using environment variables:
- `API_PORT`: Port to run the API on (default: 8003)
- `FILES_SERVICE_URL`: URL of the Files Service (default: http://files-service:8001)
- `POLL_INTERVAL`: Recommended interval for clients to poll (default: 40 seconds)

See `config.py` for all available configuration options.
