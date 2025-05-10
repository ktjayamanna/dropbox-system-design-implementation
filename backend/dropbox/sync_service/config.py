import os

# AWS Configuration
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', 'minioadmin')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', 'minioadmin')

# S3 Configuration
S3_ENDPOINT = os.environ.get('S3_ENDPOINT', 'http://minio:9000')
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', 'dropbox-chunks')
S3_USE_SSL = os.environ.get('S3_USE_SSL', 'False').lower() == 'true'

# DynamoDB Configuration
DYNAMODB_HOST = os.environ.get('DYNAMODB_HOST', 'http://dynamodb-local:8000')
DYNAMODB_REGION = os.environ.get('DYNAMODB_REGION', 'us-east-1')

# API Configuration
API_HOST = os.environ.get('API_HOST', '0.0.0.0')
API_PORT = int(os.environ.get('API_PORT', 8003))

# Files Service Configuration
FILES_SERVICE_URL = os.environ.get('FILES_SERVICE_URL', 'http://files-service:8001')

# Chunk Configuration
CHUNK_SIZE = int(os.environ.get('CHUNK_SIZE', 5 * 1024 * 1024))  # 5MB default

# Presigned URL Configuration
PRESIGNED_URL_EXPIRATION = int(os.environ.get('PRESIGNED_URL_EXPIRATION', 3600))  # 1 hour default

# Sync Configuration
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', 40))  # 40 seconds default
