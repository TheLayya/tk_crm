"""
Account CRUD API endpoints with batch operations
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.account import (
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    AccountListResponse,
    BatchAccountCreate,
    BatchAccountResult,
    BatchAccountResultItem,
    BatchActionRequest,
)
from app.services import monitor_service
from app.services.auth_service import (
    require_permission,
    get_current_user_from_header,
    get_user_data_scope,
    get_dept_member_usernames,
)
from app.models.monitor import Project
from app.services.project_service import get_visible_project_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("")
def get_accounts(
    project_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_from_header),
    _=Depends(require_permission("monitor:view")),
):
    try:
        data_scope = get_user_data_scope(db, current_user)
        dept_usernames = get_dept_member_usernames(db, current_user) if data_scope == "dept" else None
        allowed_project_ids = get_visible_project_ids(db, current_user.username, data_scope, dept_usernames)

        # 如果指定了 project_id，必须在可见范围内
        if project_id is not None and allowed_project_ids is not None and project_id not in allowed_project_ids:
            return {"items": [], "total": 0}

        total = monitor_service.count_accounts(
            db, project_id=project_id, keyword=keyword, is_active=is_active,
            allowed_project_ids=allowed_project_ids,
        )
        accounts = monitor_service.get_accounts(
            db,
            project_id=project_id,
            keyword=keyword,
            is_active=is_active,
            skip=skip,
            limit=limit,
            allowed_project_ids=allowed_project_ids,
        )

        result = []
        for account in accounts:
            account_dict = AccountResponse.model_validate(account).model_dump()
            account_dict['project_name'] = account.project.name if account.project else None
            result.append(account_dict)

        return {"items": result, "total": total}
    except Exception as e:
        logger.error(f"Failed to get accounts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve accounts",
        )


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(account_id: int, db: Session = Depends(get_db)):
    """
    Get a single account by ID.
    
    **Validates: Requirements 1.1**
    """
    try:
        account = monitor_service.get_account(db, account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account {account_id} not found",
            )
        
        # Add project_name
        account_dict = AccountResponse.model_validate(account).model_dump()
        account_dict['project_name'] = account.project.name if account.project else None
        
        return account_dict
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get account {account_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve account",
        )


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(data: AccountCreate, db: Session = Depends(get_db)):
    """
    Create a new monitor account.
    
    **Validates: Requirements 1.2, 1.3**
    
    - Triggers first check immediately and creates MonitorHistory (1.2)
    - Returns 409 if username already exists in same project (1.3)
    - Returns 404 if proxy_id is specified but proxy doesn't exist
    """
    try:
        # Validate proxy exists if specified
        if data.proxy_id is not None:
            from app.models.monitor import MonitorProxy
            proxy = db.query(MonitorProxy).filter(MonitorProxy.id == data.proxy_id).first()
            if not proxy:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Proxy {data.proxy_id} not found",
                )
        
        account = monitor_service.create_account(db, data)
        
        # Add project_name
        account_dict = AccountResponse.model_validate(account).model_dump()
        account_dict['project_name'] = account.project.name if account.project else None
        
        return account_dict
    except ValueError as e:
        # Username already exists in project
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create account: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create account",
        )


@router.put("/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: int,
    data: AccountUpdate,
    db: Session = Depends(get_db),
):
    """
    Update a monitor account.
    
    **Validates: Requirements 1.4**
    
    - Updates to monitor_interval or proxy take effect in next cycle (1.4)
    - Returns 404 if account not found
    - Returns 404 if proxy_id is specified but proxy doesn't exist
    """
    try:
        # Validate proxy exists if specified
        if data.proxy_id is not None:
            from app.models.monitor import MonitorProxy
            proxy = db.query(MonitorProxy).filter(MonitorProxy.id == data.proxy_id).first()
            if not proxy:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Proxy {data.proxy_id} not found",
                )
        
        account = monitor_service.update_account(db, account_id, data)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account {account_id} not found",
            )
        
        # Add project_name
        account_dict = AccountResponse.model_validate(account).model_dump()
        account_dict['project_name'] = account.project.name if account.project else None
        
        return account_dict
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update account {account_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update account",
        )


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    """
    Delete a monitor account.
    
    **Validates: Requirements 1.5**
    
    - Cascades deletion to all MonitorHistory and Video records (1.5)
    - Returns 404 if account not found
    """
    try:
        success = monitor_service.delete_account(db, account_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account {account_id} not found",
            )
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete account {account_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete account",
        )


@router.post("/{account_id}/check", status_code=status.HTTP_202_ACCEPTED)
async def trigger_check(account_id: int, db: Session = Depends(get_db)):
    """
    Manually trigger immediate check for a single account.
    
    **Validates: Requirements 1.6**
    
    - Triggers immediate data check and creates MonitorHistory record
    - Returns 404 if account not found
    """
    try:
        history = await monitor_service.trigger_check(db, account_id)
        if not history:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account {account_id} not found",
            )
        return {"message": "Check triggered successfully", "history_id": history.id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger check for account {account_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger check",
        )


@router.post("/import", response_model=BatchAccountResult)
def batch_import_accounts(data: BatchAccountCreate, db: Session = Depends(get_db)):
    """
    Batch import accounts from multi-line text input.
    
    **Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5**
    
    - Accepts multi-line text with one username per line (10.2)
    - Marks duplicates as "duplicate" without affecting others (10.3)
    - Marks invalid usernames as "failed" with reason (10.4)
    - Returns summary with success/duplicate/failed counts (10.5)
    """
    try:
        # Parse usernames from multi-line text
        lines = data.usernames.strip().split("\n")
        usernames = [line.strip() for line in lines if line.strip()]
        
        results = []
        success_count = 0
        duplicate_count = 0
        failed_count = 0
        
        for username in usernames:
            # 检测是否误输入了代理格式 ip:port 或 ip:port:user:pass
            parts = username.split(":")
            if len(parts) >= 2 and parts[0].replace(".", "").isdigit():
                results.append(
                    BatchAccountResultItem(
                        username=username,
                        status="failed",
                        reason="检测到代理格式，请在「代理管理」页面添加代理，此处只需填写 TikTok 用户名",
                    )
                )
                failed_count += 1
                continue

            # Validate username format (no spaces or special characters)
            if " " in username or not username.replace("_", "").replace(".", "").isalnum():
                results.append(
                    BatchAccountResultItem(
                        username=username,
                        status="failed",
                        reason="Invalid username format (contains spaces or special characters)",
                    )
                )
                failed_count += 1
                continue
            
            # Try to create account
            try:
                account_data = AccountCreate(
                    project_id=data.project_id,
                    username=username,
                    monitor_interval=data.monitor_interval,
                )
                monitor_service.create_account(db, account_data)
                results.append(
                    BatchAccountResultItem(
                        username=username,
                        status="success",
                        reason=None,
                    )
                )
                success_count += 1
            except ValueError as e:
                # Duplicate username in project
                results.append(
                    BatchAccountResultItem(
                        username=username,
                        status="duplicate",
                        reason=str(e),
                    )
                )
                duplicate_count += 1
            except Exception as e:
                results.append(
                    BatchAccountResultItem(
                        username=username,
                        status="failed",
                        reason=str(e),
                    )
                )
                failed_count += 1
        
        return BatchAccountResult(
            total=len(usernames),
            success=success_count,
            duplicates=duplicate_count,
            failed=failed_count,
            results=results,
        )
    except Exception as e:
        logger.error(f"Failed to batch import accounts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to batch import accounts",
        )


@router.post("/batch", status_code=status.HTTP_200_OK)
def batch_action(data: BatchActionRequest, db: Session = Depends(get_db)):
    """
    Perform batch operations on multiple accounts.
    
    **Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5, 11.6**
    
    - Batch enable: sets is_active=true for all specified accounts (11.1)
    - Batch disable: sets is_active=false for all specified accounts (11.2)
    - Batch delete: cascades deletion of accounts and related records (11.3)
    - Batch move: updates project_id for all specified accounts (11.4)
    - Returns 404 if target_project_id doesn't exist for move action (11.5)
    - Ignores account_ids not in current project (11.6)
    """
    try:
        if data.action == "enable":
            # Batch enable accounts
            updated = 0
            for account_id in data.account_ids:
                account = monitor_service.get_account(db, account_id)
                if account:
                    account.is_active = True
                    updated += 1
            db.commit()
            return {"message": f"Enabled {updated} accounts", "updated": updated}
        
        elif data.action == "disable":
            # Batch disable accounts
            updated = 0
            for account_id in data.account_ids:
                account = monitor_service.get_account(db, account_id)
                if account:
                    account.is_active = False
                    updated += 1
            db.commit()
            return {"message": f"Disabled {updated} accounts", "updated": updated}
        
        elif data.action == "delete":
            # Batch delete accounts (cascades to history and videos)
            deleted = 0
            for account_id in data.account_ids:
                if monitor_service.delete_account(db, account_id):
                    deleted += 1
            return {"message": f"Deleted {deleted} accounts", "deleted": deleted}
        
        elif data.action == "move":
            # Batch move accounts to target project
            if data.target_project_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="target_project_id is required for move action",
                )
            
            # Validate target project exists
            from app.models.monitor import Project
            target_project = db.query(Project).filter(Project.id == data.target_project_id).first()
            if not target_project:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Target project {data.target_project_id} not found",
                )
            
            # Move accounts
            moved = 0
            for account_id in data.account_ids:
                account = monitor_service.get_account(db, account_id)
                if account:
                    account.project_id = data.target_project_id
                    moved += 1
            db.commit()
            return {"message": f"Moved {moved} accounts to project {data.target_project_id}", "moved": moved}
        
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid action: {data.action}. Must be one of: enable, disable, delete, move",
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to perform batch action {data.action}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to perform batch action: {data.action}",
        )
