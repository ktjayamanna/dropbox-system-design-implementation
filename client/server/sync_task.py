import threading
import time
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from db.engine import SessionLocal
from db.models import System
from server.sync_client import SyncServiceClient
from server.client import FileServiceClient
from config import POLL_INTERVAL

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SyncTask:
    """
    Task for periodically polling the sync service for changes
    """
    def __init__(self, poll_interval: int = POLL_INTERVAL):
        """
        Initialize the sync task
        
        Args:
            poll_interval: Interval in seconds between polls
        """
        self.poll_interval = poll_interval
        self.sync_client = SyncServiceClient()
        self.files_client = FileServiceClient()
        self.thread = None
        self.running = False
    
    def start(self):
        """
        Start the sync task
        """
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run)
        self.thread.daemon = True
        self.thread.start()
        logger.info(f"Started sync task with poll interval of {self.poll_interval} seconds")
    
    def stop(self):
        """
        Stop the sync task
        """
        if not self.running:
            return
        
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Stopped sync task")
    
    def _run(self):
        """
        Run the sync task
        """
        while self.running:
            try:
                # Get a new database session
                db = SessionLocal()
                
                try:
                    # Get the last sync time from the database
                    last_sync_time = self._get_last_sync_time(db)
                    
                    # Poll for changes
                    response = self.sync_client.poll_for_changes(last_sync_time)
                    
                    # Process the response
                    changes_processed = self.sync_client.process_sync_response(db, response)
                    
                    if changes_processed:
                        logger.info("Changes processed successfully")
                    else:
                        logger.info("No changes to process")
                
                finally:
                    db.close()
            
            except Exception as e:
                logger.error(f"Error in sync task: {e}")
            
            # Sleep until the next poll
            time.sleep(self.poll_interval)
    
    def _get_last_sync_time(self, db: Session) -> Optional[str]:
        """
        Get the last sync time from the database
        
        Args:
            db: Database session
            
        Returns:
            ISO format timestamp of the last sync, or None if not available
        """
        try:
            system_record = db.query(System).filter(System.id == 1).first()
            if system_record and system_record.system_last_sync_time:
                return system_record.system_last_sync_time
            else:
                logger.warning("No last sync time found in database")
                return None
        except Exception as e:
            logger.error(f"Error getting last sync time: {e}")
            return None
    
    def force_sync(self) -> bool:
        """
        Force a sync immediately
        
        Returns:
            bool: True if changes were processed, False otherwise
        """
        try:
            # Get a new database session
            db = SessionLocal()
            
            try:
                # Get the last sync time from the database
                last_sync_time = self._get_last_sync_time(db)
                
                # Poll for changes
                response = self.sync_client.poll_for_changes(last_sync_time)
                
                # Process the response
                changes_processed = self.sync_client.process_sync_response(db, response)
                
                return changes_processed
            
            finally:
                db.close()
        
        except Exception as e:
            logger.error(f"Error in force sync: {e}")
            return False
