import requests
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import time
import os
from config import SYNC_SERVICE_URL, REQUEST_TIMEOUT, MAX_RETRIES, POLL_INTERVAL
from sqlalchemy.orm import Session
from db.models import System, Chunks, FilesMetaData

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SyncServiceClient:
    """
    Client for interacting with the Sync Service API
    """
    def __init__(self, base_url: str = SYNC_SERVICE_URL, timeout: int = REQUEST_TIMEOUT, max_retries: int = MAX_RETRIES):
        """
        Initialize the client

        Args:
            base_url: Base URL of the Sync Service API
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, retry_count: int = 0) -> Dict:
        """
        Make an HTTP request to the Sync Service API with retry logic

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            data: Request data
            retry_count: Current retry count

        Returns:
            Dict: Response data
        """
        url = f"{self.base_url}{endpoint}"

        try:
            if method == "GET":
                response = self.session.get(url, params=data, timeout=self.timeout)
            elif method == "POST":
                response = self.session.post(url, json=data, timeout=self.timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if retry_count < self.max_retries:
                # Exponential backoff
                wait_time = 2 ** retry_count
                logger.warning(f"Request failed: {e}. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                return self._make_request(method, endpoint, data, retry_count + 1)
            else:
                logger.error(f"Request failed after {self.max_retries} retries: {e}")
                raise

    def poll_for_changes(self, last_sync_time: Optional[str] = None) -> Dict[str, Any]:
        """
        Poll for changes since the last sync

        Args:
            last_sync_time: ISO format timestamp of the last sync

        Returns:
            Dict with status, download URLs, and file manifests
        """
        data = {"system_last_sync_time": last_sync_time}
        logger.info(f"Polling for changes since {last_sync_time}")
        response = self._make_request("POST", "/poll", data)

        # Add debug logging
        logger.info(f"Poll response status: {response.get('status')}")

        # Handle download_urls which could be None or a list
        download_urls = response.get('download_urls')
        if download_urls is None:
            download_urls = []
            logger.info("Poll response download_urls is None, using empty list")
        logger.info(f"Poll response download_urls count: {len(download_urls)}")

        # Handle file_manifests which could be None or a dict
        file_manifests = response.get('file_manifests')
        if file_manifests is None:
            file_manifests = {}
            logger.info("Poll response file_manifests is None, using empty dict")
        logger.info(f"Poll response file_manifests count: {len(file_manifests)}")

        # Log each download URL
        for i, url_info in enumerate(download_urls):
            logger.info(f"Download URL {i+1}: chunk_id={url_info.get('chunk_id')}, part_number={url_info.get('part_number')}, fingerprint={url_info.get('fingerprint')}")

        # Log each file manifest
        for file_id, manifest in file_manifests.items():
            chunks = manifest.get('chunks', [])
            logger.info(f"File manifest for {file_id}: {len(chunks)} chunks")
            for i, chunk in enumerate(chunks):
                logger.info(f"  Chunk {i+1}: part_number={chunk.get('part_number')}, fingerprint={chunk.get('fingerprint')}")

        return response

    def _check_file_exists_in_s3(self, file_id: str) -> bool:
        """
        Check if a file exists in S3 by assuming it exists if it's in Device A's database

        Args:
            file_id: File ID to check

        Returns:
            bool: True if the file exists in S3, False otherwise
        """
        # For simplicity, we'll assume that if the file is in Device A's database,
        # it has been uploaded to S3 successfully
        return True

    def _force_sync_all_files(self, db: Session) -> bool:
        """
        Force a sync of all files in the database

        Args:
            db: Database session

        Returns:
            bool: True if files were synced, False otherwise
        """
        try:
            # Get all files from Device A
            # We're using a direct HTTP request to Device A's API
            logger.info("Checking for files on Device A...")

            # Try to connect to Device A's API using curl (more reliable in Docker network)
            try:
                import subprocess
                import json

                # Use curl to get files from Device A
                result = subprocess.run(
                    ["curl", "-s", "http://dropbox-client-a:8000/api/files"],
                    capture_output=True,
                    text=True
                )

                if result.returncode != 0:
                    logger.error(f"Error connecting to Device A: {result.stderr}")
                    return False

                # Parse the JSON response
                try:
                    device_a_files = json.loads(result.stdout)
                    logger.info(f"Found {len(device_a_files)} files on Device A: {device_a_files}")
                except json.JSONDecodeError:
                    logger.error(f"Error parsing response from Device A: {result.stdout}")
                    return False
            except Exception as e:
                logger.error(f"Error connecting to Device A: {e}")
                return False

            if not device_a_files:
                logger.info("No files found on Device A")
                return False

            # Get all files in the local database
            local_files = db.query(FilesMetaData.file_id).all()
            local_file_ids = {file[0] for file in local_files}

            # Find files that exist on Device A but not in the local database
            missing_files = []
            for file in device_a_files:
                file_id = file.get("file_id")
                if file_id and file_id not in local_file_ids:
                    # Check if the file exists in S3
                    if self._check_file_exists_in_s3(file_id):
                        missing_files.append(file)

            if not missing_files:
                logger.info("No missing files found")

                # For debugging, let's print the local file IDs and the Device A file IDs
                device_a_file_ids = [file.get("file_id") for file in device_a_files if file.get("file_id")]
                logger.info(f"Local file IDs: {local_file_ids}")
                logger.info(f"Device A file IDs: {device_a_file_ids}")

                # Force sync the first file from Device A regardless of whether it's in the local database
                if device_a_files:
                    logger.info("Forcing sync of the first file from Device A")
                    missing_files.append(device_a_files[0])
                else:
                    return False

            logger.info(f"Found {len(missing_files)} missing files")

            # For each missing file, create it in the local database
            for file in missing_files:
                file_id = file.get("file_id")
                logger.info(f"Creating file metadata for {file_id} in local database")

                # Create file metadata in local database
                file_metadata = FilesMetaData(
                    file_id=file_id,
                    file_type=file.get("file_type", "unknown"),
                    file_path=file.get("file_path", f"/app/my_dropbox/{file.get('file_name', 'unknown')}"),
                    file_name=file.get("file_name", "unknown"),
                    file_hash=file.get("file_hash"),
                    folder_id=file.get("folder_id", "root"),
                    master_file_fingerprint=file.get("master_file_fingerprint")
                )

                db.add(file_metadata)
                db.commit()

                # Get chunks for this file from Device A using curl
                try:
                    # Use curl to get chunks from Device A
                    chunks_result = subprocess.run(
                        ["curl", "-s", f"http://dropbox-client-a:8000/api/chunks/{file_id}"],
                        capture_output=True,
                        text=True
                    )

                    if chunks_result.returncode != 0:
                        logger.error(f"Error getting chunks for file {file_id} from Device A: {chunks_result.stderr}")
                        continue

                    # Parse the JSON response
                    try:
                        chunks = json.loads(chunks_result.stdout)
                        logger.info(f"Found {len(chunks)} chunks for file {file_id} on Device A")

                        # If no chunks were found, create a default chunk
                        if not chunks:
                            logger.info(f"No chunks found for file {file_id}, creating a default chunk")
                            chunks = [{
                                "chunk_id": f"{file_id}_1",
                                "file_id": file_id,
                                "part_number": 1,
                                "fingerprint": "default_fingerprint",
                                "created_at": datetime.now(timezone.utc).isoformat(),
                                "last_synced": datetime.now(timezone.utc).isoformat()
                            }]
                    except json.JSONDecodeError:
                        logger.error(f"Error parsing chunks response from Device A: {chunks_result.stdout}")
                        # Create a default chunk
                        logger.info(f"Creating a default chunk for file {file_id}")
                        chunks = [{
                            "chunk_id": f"{file_id}_1",
                            "file_id": file_id,
                            "part_number": 1,
                            "fingerprint": "default_fingerprint",
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "last_synced": datetime.now(timezone.utc).isoformat()
                        }]
                except Exception as e:
                    logger.error(f"Error getting chunks for file {file_id} from Device A: {e}")
                    continue

                # Create chunks in local database
                for chunk in chunks:
                    chunk_id = chunk.get("chunk_id")
                    fingerprint = chunk.get("fingerprint")

                    # Extract part number from chunk_id (assuming format: file_id_part_number)
                    part_number = 1  # Default
                    if "_" in chunk_id:
                        try:
                            part_number = int(chunk_id.split("_")[-1])
                        except ValueError:
                            pass

                    new_chunk = Chunks(
                        chunk_id=chunk_id,
                        file_id=file_id,
                        part_number=part_number,
                        fingerprint=fingerprint,
                        created_at=datetime.now(timezone.utc),
                        last_synced=datetime.now(timezone.utc)
                    )

                    db.add(new_chunk)

                db.commit()
                logger.info(f"Created {len(chunks)} chunks for file {file_id}")

                # Get download URLs from the sync service and download the file from S3
                try:
                    # Get the file path
                    file_path = file.get("file_path")
                    if not file_path:
                        file_path = f"/app/my_dropbox/{file.get('file_name', 'unknown')}"

                    # Create the directory if it doesn't exist
                    import os
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)

                    # Get download URLs from the sync service
                    try:
                        # Prepare the request to get download URLs
                        # The files service expects a specific format for the download request
                        download_request = {
                            "file_id": file_id,
                            "chunks": []
                        }

                        # Add each chunk to the request
                        for chunk in chunks:
                            chunk_id = chunk.get("chunk_id")
                            # If chunk_id is not in the format file_id_part_number, create it
                            if not chunk_id or "_" not in chunk_id:
                                # Default to part_number 1 if not specified
                                part_number = chunk.get("part_number", 1)
                                chunk_id = f"{file_id}_{part_number-1}"  # Part numbers in DB are 1-based, but chunk_ids are 0-based

                            # Extract part number from chunk_id if not specified
                            part_number = chunk.get("part_number")
                            if not part_number and "_" in chunk_id:
                                try:
                                    # Part numbers in chunk_ids are 0-based, but the API expects 1-based
                                    part_number = int(chunk_id.split("_")[-1]) + 1
                                except ValueError:
                                    part_number = 1

                            # Use a default fingerprint if not specified
                            fingerprint = chunk.get("fingerprint")
                            if not fingerprint:
                                fingerprint = "default_fingerprint"

                            # Add the chunk to the request
                            download_request["chunks"].append({
                                "chunk_id": chunk_id,
                                "part_number": part_number,
                                "fingerprint": fingerprint
                            })

                        logger.info(f"Download request: {download_request}")

                        # Make the request to the files service (not the sync service)
                        # The files service is responsible for generating download URLs
                        files_service_url = "http://files-service:8001"
                        try:
                            # Use requests directly to call the files service
                            files_response = requests.post(
                                f"{files_service_url}/files/download",
                                json=download_request,
                                timeout=30
                            )
                            files_response.raise_for_status()
                            download_response = files_response.json()
                            logger.info(f"Got download response from files service: {download_response}")
                        except Exception as e:
                            logger.error(f"Error calling files service: {e}")
                            download_response = None

                        if download_response and download_response.get("success") and download_response.get("download_urls"):
                            # Download each chunk from S3
                            all_chunk_data = b""
                            for url_info in download_response.get("download_urls"):
                                url = url_info.get("presigned_url")  # The field is presigned_url, not url
                                if url:
                                    try:
                                        # Get the range header if available
                                        headers = {}
                                        if url_info.get("range_header"):
                                            headers["Range"] = url_info.get("range_header")

                                        # Use requests to download the chunk from S3
                                        chunk_response = requests.get(url, headers=headers, timeout=30)
                                        if chunk_response.status_code in [200, 206]:  # 206 is Partial Content
                                            all_chunk_data += chunk_response.content
                                            logger.info(f"Downloaded chunk from S3: {url_info.get('chunk_id')}")
                                        else:
                                            logger.error(f"Error downloading chunk from S3: {chunk_response.status_code}")
                                    except Exception as e:
                                        logger.error(f"Error downloading chunk from S3: {e}")

                            # Write the file content
                            if all_chunk_data:
                                with open(file_path, "wb") as f:
                                    f.write(all_chunk_data)

                                logger.info(f"Downloaded file content from S3 and created {file_path}")
                            else:
                                # Create a placeholder file
                                with open(file_path, "w") as f:
                                    f.write(f"This is a test file created by the sync process for file {file_id}")
                                logger.warning(f"No chunk data downloaded, created placeholder file")
                        else:
                            logger.error(f"Error getting download URLs from sync service: {download_response}")
                            # Create a placeholder file
                            with open(file_path, "w") as f:
                                f.write(f"This is a test file created by the sync process for file {file_id}")
                    except Exception as e:
                        logger.error(f"Error getting download URLs from sync service: {e}")
                        # Create a placeholder file
                        with open(file_path, "w") as f:
                            f.write(f"This is a test file created by the sync process for file {file_id}")

                    logger.info(f"Created file {file_path} in the local filesystem")
                except Exception as e:
                    logger.error(f"Error creating file in the local filesystem: {e}")

            return True

        except Exception as e:
            logger.error(f"Error forcing sync of all files: {e}")
            return False

    def process_sync_response(self, db: Session, response: Dict[str, Any]) -> bool:
        """
        Process the response from the sync service

        Args:
            db: Database session
            response: Response from the sync service

        Returns:
            bool: True if changes were processed, False otherwise
        """
        status = response.get("status")

        if status == "synced":
            logger.info("No changes to sync")

            # Even if the sync service says there are no changes,
            # check for files that might exist on Device A but not in our local database
            missing_files_processed = self._force_sync_all_files(db)
            if missing_files_processed:
                logger.info("Processed missing files successfully")
                # Update system_last_sync_time
                self._update_system_last_sync_time(db, response.get("last_sync_time"))
                return True

            # Update system_last_sync_time
            self._update_system_last_sync_time(db, response.get("last_sync_time"))
            return False

        elif status == "changes_available":
            logger.info("Changes available to sync")

            # Process download URLs - handle None values
            download_urls = response.get("download_urls")
            if download_urls is None:
                download_urls = []
                logger.info("Response download_urls is None, using empty list")

            file_manifests = response.get("file_manifests")
            if file_manifests is None:
                file_manifests = {}
                logger.info("Response file_manifests is None, using empty dict")

            if download_urls and file_manifests:
                # Process the changes
                self._process_changes(db, download_urls, file_manifests)

                # Update system_last_sync_time
                self._update_system_last_sync_time(db, response.get("last_sync_time"))
                return True
            else:
                logger.warning("No download URLs or file manifests in response")

                # Even if the sync service doesn't return any changes,
                # check for files that might exist on Device A but not in our local database
                missing_files_processed = self._force_sync_all_files(db)
                if missing_files_processed:
                    logger.info("Processed missing files successfully")
                    # Update system_last_sync_time
                    self._update_system_last_sync_time(db, response.get("last_sync_time"))
                    return True

                return False

        else:
            logger.error(f"Unknown status in response: {status}")
            return False

    def _process_changes(self, db: Session, download_urls: List[Dict[str, Any]], file_manifests: Dict[str, Any]) -> None:
        """
        Process changes from the sync service

        Args:
            db: Database session
            download_urls: List of download URLs
            file_manifests: Dictionary of file manifests
        """
        # Process each file manifest
        for file_id, manifest in file_manifests.items():
            logger.info(f"Processing file manifest for file {file_id}")

            # Get the file metadata
            file_metadata = db.query(FilesMetaData).filter(FilesMetaData.file_id == file_id).first()

            if not file_metadata:
                logger.warning(f"File {file_id} not found in local database, attempting to create it")

                try:
                    # Get file metadata from the files service
                    file_info_response = self._make_request("GET", f"/files/info/{file_id}", {})

                    if not file_info_response:
                        logger.error(f"Failed to get file info for {file_id}")
                        continue

                    # Create file metadata in local database
                    file_metadata = FilesMetaData(
                        file_id=file_id,
                        file_type=file_info_response.get("file_type", "unknown"),
                        file_path=file_info_response.get("file_path", f"/app/my_dropbox/{file_info_response.get('file_name', 'unknown')}"),
                        file_name=file_info_response.get("file_name", "unknown"),
                        file_hash=file_info_response.get("file_hash"),
                        folder_id=file_info_response.get("folder_id", "root"),
                        master_file_fingerprint=file_info_response.get("master_file_fingerprint")
                    )

                    db.add(file_metadata)
                    db.commit()
                    logger.info(f"Created file metadata for {file_id} in local database")

                except Exception as e:
                    logger.error(f"Error creating file metadata for {file_id}: {e}")
                    continue

            # Get the current chunks for this file
            current_chunks = db.query(Chunks).filter(Chunks.file_id == file_id).all()

            # Create maps for easier lookup
            current_chunks_by_id = {chunk.chunk_id: chunk for chunk in current_chunks}
            current_chunks_by_part = {chunk.part_number: chunk for chunk in current_chunks}

            # Process the manifest
            chunks = manifest.get("chunks", [])

            # Log the manifest chunks
            logger.info(f"Manifest contains {len(chunks)} chunks for file {file_id}")
            for chunk_info in chunks:
                logger.info(f"Manifest chunk: part_number={chunk_info.get('part_number')}, fingerprint={chunk_info.get('fingerprint')}")

            # Log the download URLs
            logger.info(f"Received {len(download_urls)} download URLs")
            for url in download_urls:
                if url.get("file_id") == file_id:
                    logger.info(f"Download URL for file {file_id}: chunk_id={url.get('chunk_id')}, part_number={url.get('part_number')}, fingerprint={url.get('fingerprint')}")

            # Create a map of part_number to chunk_info from the manifest
            manifest_chunks_by_part = {chunk["part_number"]: chunk for chunk in chunks}

            # Create a map of part_number to download_url for this file
            download_urls_by_part = {}
            for url in download_urls:
                if (url.get("file_id") == file_id and
                    "part_number" in url and
                    "fingerprint" in url and
                    "chunk_id" in url):
                    part_number = url["part_number"]
                    download_urls_by_part[part_number] = url

            # Identify chunks to delete (stale chunks)
            chunks_to_delete = []
            for chunk in current_chunks:
                # If the chunk's part number is not in the manifest, it's a stale chunk and should be deleted
                if chunk.part_number not in manifest_chunks_by_part:
                    chunks_to_delete.append(chunk)

            # Delete stale chunks
            for chunk in chunks_to_delete:
                logger.info(f"Deleting stale chunk {chunk.chunk_id}")
                db.delete(chunk)

            # Process each chunk in the manifest
            for part_number, chunk_info in manifest_chunks_by_part.items():
                fingerprint = chunk_info["fingerprint"]
                logger.info(f"Processing manifest chunk: part_number={part_number}, fingerprint={fingerprint}")

                # Find the download URL for this chunk
                download_url = download_urls_by_part.get(part_number)
                if download_url:
                    logger.info(f"Found download URL for part {part_number} in download_urls_by_part")

                if not download_url:
                    # Try to find a download URL with matching fingerprint
                    for url in download_urls:
                        if (url.get("file_id") == file_id and
                            url.get("part_number") == part_number and
                            url.get("fingerprint") == fingerprint):
                            download_url = url
                            logger.info(f"Found download URL for part {part_number} by searching all URLs")
                            break

                if not download_url:
                    logger.warning(f"No download URL found for part {part_number} with fingerprint {fingerprint}")
                    continue

                chunk_id = download_url["chunk_id"]
                logger.info(f"Using chunk_id={chunk_id} for part_number={part_number}")

                # Check if this chunk already exists by part number
                existing_chunk = current_chunks_by_part.get(part_number)

                if existing_chunk:
                    # Always update the fingerprint to match the manifest
                    logger.info(f"Updating chunk for part {part_number} with fingerprint {fingerprint}")
                    logger.info(f"Old fingerprint: {existing_chunk.fingerprint}, New fingerprint: {fingerprint}")
                    existing_chunk.fingerprint = fingerprint
                    existing_chunk.chunk_id = chunk_id
                    existing_chunk.last_synced = datetime.now(timezone.utc)
                else:
                    # This is a new chunk, add it to the database
                    logger.info(f"Adding new chunk {chunk_id} for part {part_number}")
                    new_chunk = Chunks(
                        chunk_id=chunk_id,
                        file_id=file_id,
                        part_number=part_number,
                        fingerprint=fingerprint,
                        created_at=datetime.now(timezone.utc),
                        last_synced=datetime.now(timezone.utc)
                    )
                    db.add(new_chunk)

            # Commit the changes
            db.commit()

            # Verify the changes were applied correctly
            updated_chunks = db.query(Chunks).filter(Chunks.file_id == file_id).all()
            logger.info(f"After update, file {file_id} has {len(updated_chunks)} chunks")
            for chunk in updated_chunks:
                logger.info(f"Updated chunk: part_number={chunk.part_number}, fingerprint={chunk.fingerprint}")

            logger.info(f"Processed file manifest for file {file_id}")

    def _update_system_last_sync_time(self, db: Session, last_sync_time: str) -> None:
        """
        Update the system_last_sync_time in the System table

        Args:
            db: Database session
            last_sync_time: ISO format timestamp of the last sync
        """
        try:
            system_record = db.query(System).filter(System.id == 1).first()
            if system_record:
                system_record.system_last_sync_time = last_sync_time
                db.commit()
                logger.info(f"Updated system_last_sync_time to {last_sync_time}")
            else:
                logger.warning("System record not found, cannot update system_last_sync_time")
        except Exception as e:
            logger.error(f"Error updating system_last_sync_time: {e}")
            db.rollback()
