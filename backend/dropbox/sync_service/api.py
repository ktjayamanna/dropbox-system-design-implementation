"""
API endpoints for the Sync Service.
"""
from fastapi import APIRouter, HTTPException
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from schema import PollRequest, PollResponse, DownloadUrlInfo, FileManifest, FileManifestEntry
from utils.sync import process_updated_chunks

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

@router.post("/poll", response_model=PollResponse)
async def poll_for_changes(poll_request: PollRequest):
    """
    Poll for changes since the last sync
    
    This endpoint:
    1. Accepts the client's last sync timestamp
    2. Queries DynamoDB for chunks updated after that time
    3. If no updated chunks, returns a "synced" status
    4. If updated chunks exist, generates download URLs and returns them to the client
    """
    try:
        # Get the last sync time from the request
        last_sync_time = poll_request.system_last_sync_time
        
        logger.info(f"Polling for changes since {last_sync_time}")
        
        # Process updated chunks
        result = process_updated_chunks(last_sync_time)
        
        # Convert to response model
        download_urls = []
        for url_info in result.get("download_urls", []):
            download_urls.append(DownloadUrlInfo(
                chunk_id=url_info["chunk_id"],
                part_number=url_info["part_number"],
                fingerprint=url_info["fingerprint"],
                presigned_url=url_info["presigned_url"],
                start_byte=url_info.get("start_byte"),
                end_byte=url_info.get("end_byte"),
                range_header=url_info.get("range_header")
            ))
        
        # Convert file manifests
        file_manifests = {}
        for file_id, manifest in result.get("file_manifests", {}).items():
            chunks = [
                FileManifestEntry(
                    part_number=chunk["part_number"],
                    fingerprint=chunk["fingerprint"]
                )
                for chunk in manifest["chunks"]
            ]
            file_manifests[file_id] = FileManifest(
                file_id=file_id,
                chunks=chunks
            )
        
        # Create response
        response = PollResponse(
            status=result["status"],
            download_urls=download_urls if download_urls else None,
            file_manifests=file_manifests if file_manifests else None,
            last_sync_time=result["last_sync_time"]
        )
        
        return response
    except Exception as e:
        logger.error(f"Error polling for changes: {str(e)}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Error polling for changes: {str(e)}")
