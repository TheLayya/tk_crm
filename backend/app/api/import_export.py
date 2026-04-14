"""
Import/Export API endpoints for account lists
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.account import BatchAccountResult
from app.services import import_export_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounts", tags=["Import/Export"])


@router.post("/import-file", response_model=BatchAccountResult)
async def import_accounts_from_file(
    project_id: int = Query(..., description="Target project ID"),
    file: UploadFile = File(..., description="CSV or Excel file containing usernames"),
    monitor_interval: Optional[int] = Query(None, description="Monitor interval in seconds (uses default if not specified)"),
    db: Session = Depends(get_db),
):
    """
    Import accounts from CSV or Excel file.
    
    **Validates: Requirements 12.3, 12.4, 12.5**
    
    - Parses username column and executes batch create logic (12.3)
    - Returns 422 if missing username column or unsupported format (12.4)
    - Auto-detects and skips header row (12.5)
    
    Supported formats:
    - CSV (.csv)
    - Excel (.xlsx, .xls)
    
    The file must contain a 'username' column (case-insensitive).
    Header row is automatically detected and skipped.
    """
    try:
        # Validate project exists
        from app.models.monitor import Project
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project {project_id} not found",
            )
        
        # Read file content
        content = await file.read()
        
        # Validate file is not empty
        if not content:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Uploaded file is empty",
            )
        
        # Import accounts from file
        result = await import_export_service.import_accounts_from_file(
            db=db,
            project_id=project_id,
            file_content=content,
            filename=file.filename or "unknown",
            monitor_interval=monitor_interval or 3600,  # Default 1 hour
        )
        
        return result
    
    except ValueError as e:
        # File format error or missing username column
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import accounts from file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to import accounts from file",
        )


@router.get("/export")
async def export_accounts(
    project_id: Optional[int] = Query(None, description="Project ID to export (exports all if not specified)"),
    format: str = Query("csv", pattern="^(csv|excel)$", description="Export format: csv or excel"),
    db: Session = Depends(get_db),
):
    """
    Export accounts to CSV or Excel file.
    
    **Validates: Requirements 12.1, 12.2**
    
    - Exports username, nickname, followers, last_checked, is_active fields (12.1)
    - Returns file attachment with project name and export date in filename (12.2)
    
    Supported formats:
    - csv: Comma-separated values
    - excel: Excel workbook (.xlsx)
    """
    try:
        # Get project name for filename
        project_name = "all_projects"
        if project_id is not None:
            from app.models.monitor import Project
            project = db.query(Project).filter(Project.id == project_id).first()
            if not project:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Project {project_id} not found",
                )
            project_name = project.name
        
        # Generate export date string
        export_date = datetime.now().strftime("%Y%m%d")
        
        # URL encode filename to handle non-ASCII characters (like Chinese)
        from urllib.parse import quote
        
        # Export based on format
        if format == "csv":
            content = import_export_service.export_accounts_csv(db, project_id)
            filename = f"{project_name}_accounts_{export_date}.csv"
            filename_encoded = quote(filename)
            media_type = "text/csv"
            
            return Response(
                content=content.encode("utf-8-sig"),  # UTF-8 with BOM for Excel compatibility
                media_type=media_type,
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}"
                },
            )
        
        elif format == "excel":
            content = import_export_service.export_accounts_excel(db, project_id)
            filename = f"{project_name}_accounts_{export_date}.xlsx"
            filename_encoded = quote(filename)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            
            return Response(
                content=content,
                media_type=media_type,
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}"
                },
            )
        
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported format: {format}. Must be 'csv' or 'excel'",
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export accounts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export accounts",
        )
