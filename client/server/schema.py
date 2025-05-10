from pydantic import BaseModel, field_validator
from typing import List, Optional, Dict, Any
from datetime import datetime

class FileMetaRequest(BaseModel):
    """
    Request model for creating a file in the Files Service
    """
    file_id: str  # Client-provided file ID
    file_name: str
    file_path: str
    file_type: str
    folder_id: str
    chunk_count: int
    file_hash: Optional[str] = None

    model_config = {
        "extra": "ignore"
    }

class PresignedUrlResponse(BaseModel):
    """
    Response model for a presigned URL
    """
    chunk_id: str
    presigned_url: str
    part_number: Optional[int] = None
    upload_id: Optional[str] = None

    model_config = {
        "extra": "ignore"
    }

class FileMetaResponse(BaseModel):
    """
    Response model for file creation
    """
    file_id: str
    presigned_urls: List[PresignedUrlResponse]

    model_config = {
        "extra": "ignore"
    }

class ChunkETagInfo(BaseModel):
    """
    Model for chunk ETag information
    """
    chunk_id: str
    part_number: int
    etag: str
    fingerprint: str

    model_config = {
        "extra": "ignore"
    }

class ChunkConfirmRequest(BaseModel):
    """
    Request model for confirming chunks
    """
    file_id: str
    chunk_ids: List[str]
    chunk_etags: Optional[List[Dict[str, Any]]] = None

    model_config = {
        "extra": "ignore"
    }

    @field_validator('chunk_etags')
    def validate_chunk_etags(cls, v):
        if v is not None:
            for i, chunk_info in enumerate(v):
                # Check if chunk_id is present
                if 'chunk_id' not in chunk_info:
                    raise ValueError(f"chunk_etags[{i}] missing required field 'chunk_id'")

                # Check if etag is present
                if 'etag' not in chunk_info:
                    raise ValueError(f"chunk_etags[{i}] missing required field 'etag'")

                # Check if fingerprint is present
                if 'fingerprint' not in chunk_info:
                    raise ValueError(f"chunk_etags[{i}] missing required field 'fingerprint'")
                elif not chunk_info['fingerprint']:
                    raise ValueError(f"chunk_etags[{i}] has empty fingerprint")
        return v

class ChunkConfirmResponse(BaseModel):
    """
    Response model for confirming chunks
    """
    file_id: str
    confirmed_chunks: int
    success: bool
    master_file_fingerprint: Optional[str] = None

    model_config = {
        "extra": "ignore"
    }

class FolderRequest(BaseModel):
    """
    Request model for creating/updating a folder
    """
    folder_id: str
    folder_path: str
    folder_name: str
    parent_folder_id: Optional[str] = None

    model_config = {
        "extra": "ignore"
    }

class FolderResponse(BaseModel):
    """
    Response model for folder creation/update
    """
    folder_id: str
    success: bool

    model_config = {
        "extra": "ignore"
    }

# Additional client-specific models

class FileMetadata(BaseModel):
    """
    Model for file metadata in client API responses
    """
    file_id: str
    folder_id: str
    file_path: str
    file_name: str
    file_type: str
    file_hash: Optional[str] = None
    master_file_fingerprint: Optional[str] = None

    model_config = {
        "extra": "ignore"
    }

class ChunkMetadata(BaseModel):
    """
    Model for chunk metadata in client API responses
    """
    chunk_id: str
    file_id: str
    created_at: datetime
    last_synced: Optional[datetime] = None
    fingerprint: str

    model_config = {
        "extra": "ignore"
    }

class FolderMetadata(BaseModel):
    """
    Model for folder metadata in client API responses
    """
    folder_id: str
    folder_path: str
    folder_name: str
    parent_folder_id: Optional[str] = None

    model_config = {
        "extra": "ignore"
    }

class SystemInfo(BaseModel):
    """
    Model for system information in client API responses
    """
    id: int
    system_last_sync_time: Optional[str] = None

    model_config = {
        "extra": "ignore"
    }

class SyncResponse(BaseModel):
    """
    Response model for sync operations
    """
    success: bool
    changes_processed: bool
    message: str

    model_config = {
        "extra": "ignore"
    }
