from pydantic import BaseModel, field_validator
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

class PollRequest(BaseModel):
    """
    Request model for polling for changes
    """
    system_last_sync_time: Optional[str] = None  # ISO format timestamp

    model_config = {
        "extra": "ignore"
    }

class ChunkInfo(BaseModel):
    """
    Model for chunk information
    """
    chunk_id: str
    file_id: str
    part_number: int
    fingerprint: str
    last_synced: str  # ISO format timestamp

    model_config = {
        "extra": "ignore"
    }

class DownloadUrlInfo(BaseModel):
    """
    Model for download URL information
    """
    chunk_id: str
    part_number: int
    fingerprint: str
    presigned_url: str
    start_byte: Optional[int] = None
    end_byte: Optional[int] = None
    range_header: Optional[str] = None

    model_config = {
        "extra": "ignore"
    }

class FileManifestEntry(BaseModel):
    """
    Model for a file manifest entry
    """
    part_number: int
    fingerprint: str

    model_config = {
        "extra": "ignore"
    }

class FileManifest(BaseModel):
    """
    Model for a file manifest
    """
    file_id: str
    chunks: List[FileManifestEntry]

    model_config = {
        "extra": "ignore"
    }

class PollResponse(BaseModel):
    """
    Response model for polling for changes
    """
    status: str  # "synced" or "changes_available"
    download_urls: Optional[List[DownloadUrlInfo]] = None
    file_manifests: Optional[Dict[str, FileManifest]] = None
    last_sync_time: str  # ISO format timestamp

    model_config = {
        "extra": "ignore"
    }
