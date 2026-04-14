"""
Video and VideoStats API endpoints
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.video import VideoResponse, VideoStatsResponse
from app.services import video_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Videos"])


@router.get("/accounts/{account_id}/videos")
def get_account_videos(
    account_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Get paginated list of videos for a specific account with latest stats.
    
    **Validates: Requirements 5.4**
    
    - Returns video list with latest stats and total count
    - Supports pagination with skip/limit
    - Ordered by published_at descending (newest first)
    """
    try:
        # Verify account exists
        from app.models.monitor import MonitorAccount
        from app.models.video import Video
        
        account = db.query(MonitorAccount).filter(MonitorAccount.id == account_id).first()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account {account_id} not found",
            )
        
        # Get total count
        total = db.query(Video).filter(Video.account_id == account_id).count()
        
        # Get paginated videos
        videos = video_service.get_videos(db, account_id, skip=skip, limit=limit)
        
        return {
            "items": videos,
            "total": total,
            "skip": skip,
            "limit": limit
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get videos for account {account_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve videos",
        )


@router.get("/videos/{video_id}/stats", response_model=List[VideoStatsResponse])
def get_video_stats_history(
    video_id: int,
    db: Session = Depends(get_db),
):
    """
    Get statistics history for a specific video.
    
    **Validates: Requirements 5.5**
    
    - Returns all VideoStats snapshots for trend analysis
    - Ordered by recorded_at ascending (oldest first)
    """
    try:
        # Verify video exists
        from app.models.video import Video
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video {video_id} not found",
            )
        
        stats = video_service.get_video_stats(db, video_id)
        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get stats for video {video_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve video stats",
        )


@router.post("/accounts/{account_id}/videos/collect", status_code=status.HTTP_202_ACCEPTED)
async def trigger_video_collection(
    account_id: int,
    db: Session = Depends(get_db),
):
    """
    Manually trigger video collection for a specific account.
    
    **Validates: Requirements 5.6**
    
    - Triggers immediate video collection
    - Creates VideoStats snapshots for each video
    - Returns 404 if account not found
    """
    try:
        # Verify account exists
        from app.models.monitor import MonitorAccount
        account = db.query(MonitorAccount).filter(MonitorAccount.id == account_id).first()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account {account_id} not found",
            )
        
        # Trigger video collection
        new_count = await video_service.fetch_and_save_videos(db, account)
        
        return {
            "message": "Video collection triggered successfully",
            "account_id": account_id,
            "new_videos": new_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger video collection for account {account_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger video collection",
        )
