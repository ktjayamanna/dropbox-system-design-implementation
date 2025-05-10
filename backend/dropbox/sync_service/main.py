"""
Main application file for the Sync Service.
"""
from fastapi import FastAPI
import logging

import config
from api import router as api_router

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/tmp/sync_service.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

logger.info("Sync Service starting up")

app = FastAPI(
    title="Sync Service API",
    description="API for handling file synchronization",
    version="0.1.0"
)

# Include API router
app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=True
    )
