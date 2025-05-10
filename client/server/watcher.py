import pyinotify
import os
import uuid
import time
import threading
from db.engine import SessionLocal
from db.models import FilesMetaData, Chunks, Folders
from server.sync import SyncEngine
from typing import Callable
from config import SYNC_DIR

class EventHandler(pyinotify.ProcessEvent):
    def __init__(self, sync_dir: str, callback: Callable = None):
        """
        Initialize the event handler

        Args:
            sync_dir: Directory to watch
            callback: Callback function to call when events occur
        """
        self.sync_dir = sync_dir
        self.callback = callback
        # Dictionary to track files that are currently being modified
        # Keys are file paths, values are booleans indicating if they've been modified
        self.modified_files = {}
        super().__init__()

    def process_IN_CREATE(self, event):
        """
        Handle file or directory creation events

        Args:
            event: Inotify event
        """
        if event.dir:
            print(f"Directory created: {event.pathname}")
            if self.callback:
                self.callback('create_dir', event.pathname)
        else:
            print(f"File created: {event.pathname}")
            if self.callback:
                self.callback('create', event.pathname)

    def process_IN_MODIFY(self, event):
        """
        Handle file modification events

        Instead of immediately syncing the file, we mark it as modified
        and wait for the IN_CLOSE_WRITE event to sync it.

        Args:
            event: Inotify event
        """
        if not event.dir:  # Directories don't have content to modify
            print(f"File modified: {event.pathname}")
            # Mark the file as modified with the current timestamp
            self.modified_files[event.pathname] = time.time()
            print(f"Marked file as modified (waiting for close): {event.pathname}")

    def process_IN_CLOSE_WRITE(self, event):
        """
        Handle file close write events

        This event occurs when a file that was open for writing is closed.
        If the file was previously modified, we sync it now.

        Args:
            event: Inotify event
        """
        if not event.dir and event.pathname in self.modified_files:
            print(f"File closed after write: {event.pathname}")
            # Remove the file from the modified files dictionary
            del self.modified_files[event.pathname]
            # Sync the file now that it's been completely written
            if self.callback:
                self.callback('close_write', event.pathname)

    def process_IN_DELETE(self, event):
        """
        Handle file or directory deletion events

        Args:
            event: Inotify event
        """
        if event.dir:
            print(f"Directory deleted: {event.pathname}")
            if self.callback:
                self.callback('delete_dir', event.pathname)
        else:
            print(f"File deleted: {event.pathname}")
            if self.callback:
                self.callback('delete', event.pathname)

    def process_IN_MOVED_FROM(self, event):
        """
        Handle file or directory move from events

        Args:
            event: Inotify event
        """
        if event.dir:
            print(f"Directory moved from: {event.pathname}")
            if self.callback:
                self.callback('move_from_dir', event.pathname)
        else:
            print(f"File moved from: {event.pathname}")
            if self.callback:
                self.callback('move_from', event.pathname)

    def process_IN_MOVED_TO(self, event):
        """
        Handle file or directory move to events

        Args:
            event: Inotify event
        """
        if event.dir:
            print(f"Directory moved to: {event.pathname}")
            if self.callback:
                self.callback('move_to_dir', event.pathname)
        else:
            print(f"File moved to: {event.pathname}")
            if self.callback:
                self.callback('move_to', event.pathname)

class Watcher:
    def __init__(self, sync_dir: str = SYNC_DIR, modified_file_timeout: int = 30):
        """
        Initialize the watcher

        Args:
            sync_dir: Directory to watch (defaults to SYNC_DIR from config)
            modified_file_timeout: Time in seconds to wait before syncing modified files
                                  that haven't received a close_write event (default: 30)
        """
        self.sync_dir = sync_dir
        self.wm = pyinotify.WatchManager()
        self.handler = EventHandler(sync_dir, self.handle_event)
        self.notifier = None
        self.thread = None
        self.cleanup_thread = None
        self.running = False
        self.modified_file_timeout = modified_file_timeout

    def start(self):
        """
        Start watching the directory and scan existing files
        """
        if self.running:
            return

        # Create directory if it doesn't exist
        os.makedirs(self.sync_dir, exist_ok=True)

        # Scan existing files in the sync directory
        self.scan_existing_files()

        # Set up inotify
        mask = pyinotify.IN_CREATE | pyinotify.IN_MODIFY | pyinotify.IN_DELETE | pyinotify.IN_MOVED_FROM | pyinotify.IN_MOVED_TO | pyinotify.IN_CLOSE_WRITE
        self.notifier = pyinotify.ThreadedNotifier(self.wm, self.handler)
        self.wm.add_watch(self.sync_dir, mask, rec=True, auto_add=True)

        # Start the notifier
        self.notifier.start()
        self.running = True

        # Start the cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_modified_files)
        self.cleanup_thread.daemon = True
        self.cleanup_thread.start()

        print(f"Started watching directory: {self.sync_dir}")

    def _cleanup_modified_files(self):
        """
        Periodically check for files that were modified but never received a close_write event
        and sync them after a timeout period.
        """
        while self.running:
            # Sleep for a short time to avoid high CPU usage
            time.sleep(5)

            # Make a copy of the modified files dictionary to avoid modification during iteration
            modified_files = self.handler.modified_files.copy()

            # Check each modified file
            for path, modified_time in list(modified_files.items()):
                # If the file has been modified for longer than the timeout, sync it
                if isinstance(modified_time, float) and time.time() - modified_time > self.modified_file_timeout:
                    print(f"Timeout reached for modified file: {path}")
                    # Remove the file from the modified files dictionary
                    if path in self.handler.modified_files:
                        del self.handler.modified_files[path]
                    # Sync the file
                    self.handle_event('close_write', path)

    def scan_existing_files(self):
        """
        Scan existing files in the sync directory and process them
        Also clean up any orphaned chunks
        """
        print(f"Scanning existing files in: {self.sync_dir}")

        # Get a new database session
        db = SessionLocal()
        try:
            # Create sync engine
            sync_engine = SyncEngine(db, self.sync_dir)

            # Scan the sync directory
            sync_engine.scan_sync_directory()

            # Clean up orphaned chunks
            sync_engine.cleanup_orphaned_chunks()

        finally:
            db.close()

    def stop(self):
        """
        Stop watching the directory
        """
        if not self.running:
            return

        # Stop the notifier
        self.notifier.stop()
        self.running = False

        # Wait for the cleanup thread to finish
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            self.cleanup_thread.join(timeout=2)  # Wait up to 2 seconds

        print(f"Stopped watching directory: {self.sync_dir}")

    def handle_event(self, event_type: str, path: str):
        """
        Handle file and directory events

        Args:
            event_type: Type of event (create, modify, delete, move_from, move_to,
                        create_dir, delete_dir, move_from_dir, move_to_dir)
            path: Path to the file or directory
        """
        # Get a new database session
        db = SessionLocal()
        try:
            # Create sync engine
            sync_engine = SyncEngine(db, self.sync_dir)

            # Handle event based on type
            if event_type == 'create':
                # Upload file immediately for create events
                file_id = sync_engine.upload_file(path)
                print(f"Uploaded file: {path} with ID: {file_id}")
            elif event_type == 'modify':
                # For modify events, we don't do anything here
                # We'll wait for the close_write event to sync the file
                print(f"Skipping sync for modified file (waiting for close): {path}")
            elif event_type == 'close_write':
                # This is called when a file that was open for writing is closed
                # and it was previously modified
                file_id = sync_engine.upload_file(path)
                print(f"Uploaded file after close_write: {path} with ID: {file_id}")

            elif event_type == 'create_dir':
                # Skip if this is the sync directory itself
                if path == self.sync_dir:
                    return

                # Create directory entry and ensure parent directories exist
                folder_id = sync_engine._ensure_folder_tree(path)
                print(f"Added directory to database: {path} with ID: {folder_id}")

                # Scan the directory for any existing files
                print(f"Scanning new directory: {path}")
                for root, _, files in os.walk(path):
                    for filename in files:
                        file_path = os.path.join(root, filename)

                        # Skip hidden files
                        if filename.startswith('.'):
                            continue

                        try:
                            # Process the file
                            file_id = sync_engine.upload_file(file_path)
                            print(f"Processed file in new directory: {file_path} with ID: {file_id}")
                        except Exception as e:
                            print(f"Error processing file {file_path}: {e}")

            elif event_type == 'delete':
                # Delete file entry and its chunks
                file_metadata = db.query(FilesMetaData).filter(
                    FilesMetaData.file_path == path
                ).first()

                if file_metadata:
                    # Delete chunks
                    db.query(Chunks).filter(Chunks.file_id == file_metadata.file_id).delete()
                    # Delete file metadata
                    db.delete(file_metadata)
                    db.commit()
                    print(f"Deleted file from database: {path}")

                    # Clean up orphaned chunks
                    sync_engine.cleanup_orphaned_chunks()

            elif event_type == 'delete_dir':
                # Delete directory entry and all its contents
                folder = db.query(Folders).filter(
                    Folders.folder_path == path
                ).first()

                if folder:
                    # Get all files in this folder and its subfolders
                    files_to_delete = db.query(FilesMetaData).filter(
                        FilesMetaData.folder_id == folder.folder_id
                    ).all()

                    # Delete chunks for all files
                    for file in files_to_delete:
                        db.query(Chunks).filter(Chunks.file_id == file.file_id).delete()
                        db.delete(file)

                    # Delete the folder (cascade will delete subfolders)
                    db.delete(folder)
                    db.commit()
                    print(f"Deleted directory and its contents from database: {path}")

                    # Clean up orphaned chunks
                    sync_engine.cleanup_orphaned_chunks()

            elif event_type == 'move_to_dir':
                # Handle directory moved to the sync directory
                print(f"Handling directory moved to sync directory: {path}")

                # Special handling for top-level directories moved directly to the sync directory
                if os.path.dirname(path) == sync_engine.sync_dir:
                    print(f"Top-level directory moved to sync directory, setting parent to root folder")
                    # Get the root folder
                    root_folder = sync_engine._get_or_create_root_folder()

                    # Create the folder with the root folder as parent
                    folder_name = os.path.basename(path)
                    folder_id = str(uuid.uuid4())

                    # Create folder in local database
                    folder = Folders(
                        folder_id=folder_id,
                        folder_path=path,
                        folder_name=folder_name,
                        parent_folder_id=None  # Set parent to null for top-level folders
                    )

                    db.add(folder)
                    db.commit()
                    print(f"Added top-level moved directory to database: {path} with ID: {folder_id}")

                    # Sync folder with server
                    try:
                        from server.client import FileServiceClient
                        api_client = FileServiceClient()

                        # Send folder information to server
                        response = api_client.create_folder(
                            folder_id=folder_id,
                            folder_path=path,
                            folder_name=folder_name,
                            parent_folder_id=root_folder.folder_id
                        )

                        if response.get('success'):
                            print(f"Successfully synced folder {path} with server")
                        else:
                            print(f"Failed to sync folder {path} with server: {response}")
                    except Exception as e:
                        print(f"Error syncing folder {path} with server: {e}")
                else:
                    # For subdirectories, use the normal folder tree creation
                    folder_id = sync_engine._ensure_folder_tree(path)
                    print(f"Added moved directory to database: {path} with ID: {folder_id}")

                # Scan the directory for any existing files
                print(f"Scanning moved directory: {path}")
                for root, dirs, files in os.walk(path):
                    # First, ensure all subdirectories are in the database
                    for dir_name in dirs:
                        dir_path = os.path.join(root, dir_name)
                        subdir_folder_id = sync_engine._ensure_folder_tree(dir_path)
                        print(f"Added subdirectory to database: {dir_path} with ID: {subdir_folder_id}")

                    # Then process all files in this directory
                    for filename in files:
                        file_path = os.path.join(root, filename)

                        # Skip hidden files
                        if filename.startswith('.'):
                            continue

                        try:
                            # Get the folder ID for this file's directory
                            file_dir = os.path.dirname(file_path)
                            folder = db.query(Folders).filter(Folders.folder_path == file_dir).first()

                            if folder:
                                # Calculate file hash for content tracking
                                file_hash = sync_engine.calculate_file_hash(file_path)

                                # Get file type from extension
                                _, file_extension = os.path.splitext(filename)
                                file_type = file_extension[1:] if file_extension else "unknown"

                                # Create file metadata with the correct folder ID
                                file_id = str(uuid.uuid4())
                                file_metadata = FilesMetaData(
                                    file_id=file_id,
                                    file_type=file_type,
                                    file_path=file_path,
                                    folder_id=folder.folder_id,  # Use the correct folder ID
                                    file_name=filename,
                                    file_hash=file_hash
                                )

                                # Add to database
                                db.add(file_metadata)
                                db.commit()
                                print(f"Added file to database with correct folder: {file_path} with ID: {file_id}")

                                # Process file chunks
                                sync_engine._process_file_chunks(file_path, file_id)
                            else:
                                # Fallback to normal upload if folder not found
                                file_id = sync_engine.upload_file(file_path)
                                print(f"Processed file in moved directory: {file_path} with ID: {file_id}")
                        except Exception as e:
                            print(f"Error processing file {file_path}: {e}")

            elif event_type == 'move_to':
                # Handle file moved to the sync directory
                print(f"Handling file moved to sync directory: {path}")

                # Get the folder ID for this file's directory
                file_dir = os.path.dirname(path)
                folder = db.query(Folders).filter(Folders.folder_path == file_dir).first()

                if folder:
                    print(f"Found folder for file: {folder.folder_name} (ID: {folder.folder_id})")
                    # Calculate file hash for content tracking
                    file_hash = sync_engine.calculate_file_hash(path)

                    # Extract file name
                    file_name = os.path.basename(path)

                    # Get file type from extension
                    _, file_extension = os.path.splitext(path)
                    file_type = file_extension[1:] if file_extension else "unknown"

                    # Create file metadata with the correct folder ID
                    file_id = str(uuid.uuid4())
                    file_metadata = FilesMetaData(
                        file_id=file_id,
                        file_type=file_type,
                        file_path=path,
                        folder_id=folder.folder_id,  # Use the correct folder ID
                        file_name=file_name,
                        file_hash=file_hash
                    )

                    # Add to database
                    db.add(file_metadata)
                    db.commit()
                    print(f"Added file to database with correct folder: {path} with ID: {file_id}")

                    # Process file chunks
                    sync_engine._process_file_chunks(path, file_id)
                else:
                    # For files without a matching folder, use the normal upload process
                    file_id = sync_engine.upload_file(path)
                    print(f"Uploaded moved file: {path} with ID: {file_id}")

        finally:
            db.close()
