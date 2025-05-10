"""
Sync-related helper functions for the Sync Service.
"""
import logging
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import config
from utils.db import get_updated_chunks, get_file_manifest

logger = logging.getLogger(__name__)

def get_download_urls_from_files_service(chunk_infos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Get download URLs for chunks from the Files Service

    Args:
        chunk_infos: List of dictionaries containing chunk_id, part_number, and fingerprint

    Returns:
        List of dictionaries containing download URLs and chunk information
    """
    try:
        # Prepare request to Files Service
        url = f"{config.FILES_SERVICE_URL}/files/download"

        # Group chunks by file_id
        chunks_by_file = {}
        for chunk_info in chunk_infos:
            file_id = chunk_info["file_id"]
            if file_id not in chunks_by_file:
                chunks_by_file[file_id] = []

            chunks_by_file[file_id].append({
                "chunk_id": chunk_info["chunk_id"],
                "part_number": chunk_info["part_number"],
                "fingerprint": chunk_info["fingerprint"]
            })

        # Make requests to Files Service for each file
        all_download_urls = []
        for file_id, chunks in chunks_by_file.items():
            payload = {
                "file_id": file_id,
                "chunks": chunks
            }

            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()

            response_data = response.json()
            if response_data.get("success"):
                # Add file_id to each download URL
                download_urls = response_data.get("download_urls", [])
                for url_info in download_urls:
                    url_info["file_id"] = file_id
                all_download_urls.extend(download_urls)
            else:
                logger.error(f"Error getting download URLs from Files Service: {response_data.get('error_message')}")

        return all_download_urls
    except requests.exceptions.RequestException as e:
        logger.error(f"Error communicating with Files Service: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"Error getting download URLs: {str(e)}")
        return []

def process_updated_chunks(last_sync_time: Optional[str]) -> Dict[str, Any]:
    """
    Process chunks that have been updated since the last sync time

    Args:
        last_sync_time: ISO format timestamp of the last sync

    Returns:
        Dictionary with status, download URLs, and file manifests
    """
    try:
        # Handle potential malformed timestamps in the last_sync_time
        if isinstance(last_sync_time, str):
            if 'Z' in last_sync_time:
                last_sync_time = last_sync_time.replace('Z', '+00:00')

            # Handle the specific malformed timestamp format we're seeing in the logs
            if last_sync_time.startswith('00000002025'):
                # Extract the actual timestamp part starting from the year
                last_sync_time = last_sync_time[7:]  # Remove the leading '0000000'
                logger.info(f"Fixed specific malformed last_sync_time: {last_sync_time}")
            # Handle any malformed timestamp format with leading zeros
            elif last_sync_time.startswith('0'):
                # Find the position of the year (2025)
                year_pos = last_sync_time.find('2025')
                if year_pos >= 0:
                    # Extract the actual timestamp part starting from the year
                    last_sync_time = last_sync_time[year_pos:]
                    logger.info(f"Fixed malformed last_sync_time with leading zeros: {last_sync_time}")
                else:
                    # If we can't find the year, try removing all leading zeros
                    fixed_timestamp = last_sync_time.lstrip('0')
                    if fixed_timestamp.startswith('2'):  # Make sure it starts with a year
                        last_sync_time = fixed_timestamp
                        logger.info(f"Fixed malformed last_sync_time by removing leading zeros: {last_sync_time}")
    except Exception as e:
        logger.warning(f"Error preprocessing last_sync_time: {str(e)}")

    # Get updated chunks
    updated_chunks = get_updated_chunks(last_sync_time)

    if not updated_chunks:
        # No updated chunks, return synced status
        current_time = datetime.now(timezone.utc).isoformat()
        return {
            "status": "synced",
            "download_urls": [],
            "file_manifests": {},
            "last_sync_time": current_time
        }

    # Prepare chunk info for getting download URLs
    chunk_infos = [
        {
            "chunk_id": chunk.chunk_id,
            "file_id": chunk.file_id,
            "part_number": chunk.part_number,
            "fingerprint": chunk.fingerprint
        }
        for chunk in updated_chunks
    ]

    # Get download URLs from Files Service
    download_urls = get_download_urls_from_files_service(chunk_infos)

    # Get unique file IDs from updated chunks
    file_ids = set(chunk.file_id for chunk in updated_chunks)

    # Get file manifests for each file
    file_manifests = {}
    for file_id in file_ids:
        manifest = get_file_manifest(file_id)
        file_manifests[file_id] = manifest

    # Return response
    current_time = datetime.now(timezone.utc).isoformat()
    return {
        "status": "changes_available",
        "download_urls": download_urls,
        "file_manifests": file_manifests,
        "last_sync_time": current_time
    }
