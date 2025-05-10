from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.engine import get_db
from db.models import FilesMetaData, Chunks, Folders, System
from typing import List, Dict, Any
from server.schema import FileMetadata, ChunkMetadata, FolderMetadata, SystemInfo, SyncResponse
import server.main as main_module

router = APIRouter()

@router.get("/folders", response_model=List[FolderMetadata])
def get_folders(db: Session = Depends(get_db)):
    """Get all folders"""
    folders = db.query(Folders).all()
    return [
        FolderMetadata(
            folder_id=folder.folder_id,
            folder_path=folder.folder_path,
            folder_name=folder.folder_name,
            parent_folder_id=folder.parent_folder_id
        )
        for folder in folders
    ]

@router.get("/folders/{folder_id}", response_model=FolderMetadata)
def get_folder(folder_id: str, db: Session = Depends(get_db)):
    """Get folder by ID"""
    folder = db.query(Folders).filter(Folders.folder_id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return FolderMetadata(
        folder_id=folder.folder_id,
        folder_path=folder.folder_path,
        folder_name=folder.folder_name,
        parent_folder_id=folder.parent_folder_id
    )

@router.get("/files", response_model=List[FileMetadata])
def get_files(db: Session = Depends(get_db)):
    """Get all files metadata"""
    files = db.query(FilesMetaData).all()
    return [
        FileMetadata(
            file_id=file.file_id,
            folder_id=file.folder_id,
            file_path=file.file_path,
            file_name=file.file_name,
            file_type=file.file_type,
            file_hash=file.file_hash
        )
        for file in files
    ]

@router.get("/files/{file_id}", response_model=FileMetadata)
def get_file(file_id: str, db: Session = Depends(get_db)):
    """Get file metadata by ID"""
    file = db.query(FilesMetaData).filter(FilesMetaData.file_id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    return FileMetadata(
        file_id=file.file_id,
        folder_id=file.folder_id,
        file_path=file.file_path,
        file_name=file.file_name,
        file_type=file.file_type,
        file_hash=file.file_hash
    )

@router.get("/chunks/{file_id}", response_model=List[ChunkMetadata])
def get_chunks(file_id: str, db: Session = Depends(get_db)):
    """Get all chunks for a file"""
    chunks = db.query(Chunks).filter(Chunks.file_id == file_id).all()
    return [
        ChunkMetadata(
            chunk_id=chunk.chunk_id,
            file_id=chunk.file_id,
            created_at=chunk.created_at,
            last_synced=chunk.last_synced,
            fingerprint=chunk.fingerprint
        )
        for chunk in chunks
    ]

@router.get("/system", response_model=SystemInfo)
def get_system_info(db: Session = Depends(get_db)):
    """Get system information including last sync time"""
    system = db.query(System).filter(System.id == 1).first()
    if not system:
        raise HTTPException(status_code=404, detail="System information not found")
    return SystemInfo(
        id=system.id,
        system_last_sync_time=system.system_last_sync_time
    )

@router.post("/sync", response_model=SyncResponse)
def force_sync():
    """Force a sync with the server"""
    try:
        # Get the sync task from the main module
        sync_task = main_module.sync_task

        # Force a sync
        changes_processed = sync_task.force_sync()

        return SyncResponse(
            success=True,
            changes_processed=changes_processed,
            message="Sync completed successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error forcing sync: {str(e)}")
