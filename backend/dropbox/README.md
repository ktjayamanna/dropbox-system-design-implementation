# Dropbox Backend Services

This directory contains the backend microservices for the Dropbox system.

## Services

1. **Files Service** - Handles file metadata and multipart uploads
   - Provides endpoints for receiving file metadata and generating presigned URLs
   - Confirms successful multipart uploads and updates chunk status
   - Generates download URLs for file chunks
   - Uses PynamoDB to interact with DynamoDB for data storage

2. **Sync Service** - Handles file synchronization between clients and server
   - Provides polling endpoint for clients to check for changes
   - Queries DynamoDB for updated chunks
   - Coordinates with Files Service to help clients download and organize file chunks
   - Uses PynamoDB to interact with DynamoDB for data storage

## Directory Structure

```
backend/dropbox/
├── files_service/       # Files microservice
│   ├── config.py        # Configuration settings
│   ├── main.py          # FastAPI application
│   ├── models.py        # PynamoDB models
│   ├── requirements.txt # Python dependencies
│   └── utils/           # Utility functions
├── sync_service/        # Sync microservice
│   ├── config.py        # Configuration settings
│   ├── main.py          # FastAPI application
│   ├── schema.py        # Pydantic models
│   ├── requirements.txt # Python dependencies
│   └── utils/           # Utility functions
└── README.md            # This file
```

## Deployment

The services are deployed using Docker. See the `deployment/backend` directory for Docker configuration and deployment scripts.
