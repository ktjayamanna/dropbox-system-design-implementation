from fastapi import FastAPI
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from server.api import router as api_router
from server.watcher import Watcher
from server.sync_task import SyncTask
from config import SYNC_DIR, CHUNK_DIR
from db.engine import SessionLocal
from db.models import System

# Create FastAPI app
@asynccontextmanager
async def lifespan(app):
    # Start the file watcher and sync task when the application starts
    watcher.start()
    sync_task.start()
    yield
    # Stop the file watcher and sync task when the application shuts down
    watcher.stop()
    sync_task.stop()

app = FastAPI(
    title="Dropbox Client API",
    description="API for Dropbox client synchronization",
    lifespan=lifespan
)

# Create necessary directories if they don't exist
os.makedirs(SYNC_DIR, exist_ok=True)
os.makedirs(CHUNK_DIR, exist_ok=True)

# Verify directories exist and are writable
print(f"Sync directory: {SYNC_DIR} (exists: {os.path.exists(SYNC_DIR)}, writable: {os.access(SYNC_DIR, os.W_OK)})")
print(f"Chunk directory: {CHUNK_DIR} (exists: {os.path.exists(CHUNK_DIR)}, writable: {os.access(CHUNK_DIR, os.W_OK)})")

# Create a test file in the chunk directory to verify it's working
test_file_path = os.path.join(CHUNK_DIR, "test_file.txt")
try:
    with open(test_file_path, 'w') as f:
        f.write("Test file to verify chunk directory is working")
    print(f"Successfully created test file at {test_file_path}")
    os.remove(test_file_path)
    print(f"Successfully removed test file at {test_file_path}")
except Exception as e:
    print(f"Error accessing chunk directory: {e}")

# Initialize System table with a singleton record if it doesn't exist
try:
    db = SessionLocal()
    system_record = db.query(System).filter(System.id == 1).first()
    if not system_record:
        print("Initializing System table with singleton record...")
        system_record = System(id=1, system_last_sync_time=datetime.now(timezone.utc).isoformat())
        db.add(system_record)
        db.commit()
        print("System table initialized successfully")
    else:
        print("System table singleton record already exists")
    db.close()
except Exception as e:
    print(f"Error initializing System table: {e}")

@app.get("/")
def read_root():
    return {"message": "Welcome to Dropbox Client API"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

# Include routers
app.include_router(api_router, prefix="/api")

# Initialize file watcher and sync task
watcher = Watcher()
sync_task = SyncTask()
