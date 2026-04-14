"""
History and trend data API endpoints
"""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.core.database import get_db
from app.models.monitor import MonitorAccount, MonitorHistory
from app.schemas.history import HistoryResponse, TrendDataPoint, TrendResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounts", tags=["History"])


@router.get("/{account_id}/history", response_model=List[HistoryResponse])
def get_account_history(
    account_id: int,
    start_time: Optional[datetime] = Query(None, description="Start of time range filter"),
    end_time: Optional[datetime] = Query(None, description="End of time range filter"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Get historical records for a monitor account with time range filtering.
    
    **Validates: Requirements 3.1**
    
    - Returns MonitorHistory list in descending order by checked_at
    - Supports time range filtering with start_time and end_time
    - Supports pagination with skip/limit
    - Returns 404 if account not found
    """
    try:
        # Verify account exists
        account = db.query(MonitorAccount).filter(MonitorAccount.id == account_id).first()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account {account_id} not found",
            )
        
        # Build query with filters
        query = db.query(MonitorHistory).filter(MonitorHistory.account_id == account_id)
        
        # Apply time range filters
        if start_time is not None:
            query = query.filter(MonitorHistory.checked_at >= start_time)
        if end_time is not None:
            query = query.filter(MonitorHistory.checked_at <= end_time)
        
        # Order by checked_at descending and paginate
        history = (
            query.order_by(MonitorHistory.checked_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        
        return history
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get history for account {account_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve history",
        )


@router.get("/{account_id}/trends", response_model=TrendResponse)
def get_account_trends(
    account_id: int,
    start_time: Optional[datetime] = Query(None, description="Start of time range filter"),
    end_time: Optional[datetime] = Query(None, description="End of time range filter"),
    db: Session = Depends(get_db),
):
    """
    Get trend data with calculated deltas between adjacent records.
    
    **Validates: Requirements 3.2, 3.3**
    
    - Returns time series data points with follower_count, like_count, video_count
    - Calculates followers_change and likes_change between adjacent records (3.3)
    - Supports time range filtering with start_time and end_time (3.2)
    - Returns 404 if account not found
    """
    try:
        # Verify account exists
        account = db.query(MonitorAccount).filter(MonitorAccount.id == account_id).first()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account {account_id} not found",
            )
        
        # Build query with filters
        query = db.query(MonitorHistory).filter(MonitorHistory.account_id == account_id)
        
        # Apply time range filters
        if start_time is not None:
            query = query.filter(MonitorHistory.checked_at >= start_time)
        if end_time is not None:
            query = query.filter(MonitorHistory.checked_at <= end_time)
        
        # Order by checked_at ascending for trend calculation
        history = query.order_by(MonitorHistory.checked_at.asc()).all()
        
        # Build trend data points with deltas
        data_points = []
        for i, record in enumerate(history):
            # Calculate deltas from previous record
            if i > 0:
                prev_record = history[i - 1]
                followers_change = record.follower_count - prev_record.follower_count
                likes_change = record.like_count - prev_record.like_count
            else:
                # First record has no previous, delta is 0
                followers_change = 0
                likes_change = 0
            
            data_points.append(
                TrendDataPoint(
                    checked_at=record.checked_at,
                    follower_count=record.follower_count,
                    following_count=record.following_count,
                    like_count=record.like_count,
                    video_count=record.video_count,
                    followers_change=followers_change,
                    likes_change=likes_change,
                )
            )
        
        return TrendResponse(data_points=data_points)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get trends for account {account_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve trends",
        )
