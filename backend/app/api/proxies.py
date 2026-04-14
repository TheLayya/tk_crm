"""
Proxy CRUD API endpoints with connectivity testing
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.proxy import ProxyCreate, ProxyUpdate, ProxyResponse, ProxyTestResult, ProxyBatchCreate, ProxyBatchResult
from app.services import proxy_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/proxies", tags=["Proxies"])


@router.post("/batch", response_model=ProxyBatchResult, status_code=status.HTTP_201_CREATED)
def batch_create_proxies(data: ProxyBatchCreate, db: Session = Depends(get_db)):
    """
    Batch create proxies from text input.
    
    Supports format: ip:port:username:password or ip:port
    Each line is one proxy.
    
    Example:
    ```
    192.168.1.1:8080:user1:pass1
    192.168.1.2:8080
    192.168.1.3:1080:user3:pass3
    ```
    """
    try:
        lines = [line.strip() for line in data.proxies_text.strip().split('\n') if line.strip()]
        
        success_count = 0
        fail_count = 0
        errors = []
        created_proxies = []
        
        for idx, line in enumerate(lines, 1):
            try:
                parts = line.split(':')
                if len(parts) < 2:
                    errors.append(f"行 {idx}: 格式错误，至少需要 ip:port")
                    fail_count += 1
                    continue
                
                host = parts[0]
                try:
                    port = int(parts[1])
                except ValueError:
                    errors.append(f"行 {idx}: 端口号必须是数字")
                    fail_count += 1
                    continue
                
                username = parts[2] if len(parts) > 2 else None
                password = parts[3] if len(parts) > 3 else None
                
                # 生成代理名称
                name = f"{host}:{port}"
                if username:
                    name = f"{username}@{host}:{port}"
                
                proxy_data = ProxyCreate(
                    name=name,
                    proxy_type=data.proxy_type,
                    host=host,
                    port=port,
                    username=username,
                    password=password,
                    is_active=data.is_active,
                    is_global=False
                )
                
                proxy = proxy_service.create_proxy(db, proxy_data)
                created_proxies.append(proxy)
                success_count += 1
                
            except Exception as e:
                errors.append(f"行 {idx}: {str(e)}")
                fail_count += 1
        
        return ProxyBatchResult(
            success_count=success_count,
            fail_count=fail_count,
            errors=errors,
            created_proxies=created_proxies
        )
        
    except Exception as e:
        logger.error(f"Failed to batch create proxies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to batch create proxies",
        )


@router.get("", response_model=List[ProxyResponse])
def get_proxies(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    Get paginated list of proxies.
    
    **Validates: Requirements 4.1**
    
    - Returns list of all proxies with pagination
    - Each proxy includes protocol type, host, port, credentials (username only, not password)
    """
    try:
        proxies = proxy_service.get_proxies(db, skip=skip, limit=limit)
        return proxies
    except Exception as e:
        logger.error(f"Failed to get proxies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve proxies",
        )


@router.get("/{proxy_id}", response_model=ProxyResponse)
def get_proxy(proxy_id: int, db: Session = Depends(get_db)):
    """
    Get a single proxy by ID.
    
    **Validates: Requirements 4.1**
    """
    try:
        proxy = proxy_service.get_proxy(db, proxy_id)
        if not proxy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Proxy {proxy_id} not found",
            )
        return proxy
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get proxy {proxy_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve proxy",
        )


@router.post("", response_model=ProxyResponse, status_code=status.HTTP_201_CREATED)
def create_proxy(data: ProxyCreate, db: Session = Depends(get_db)):
    """
    Create a new proxy.
    
    **Validates: Requirements 4.1**
    
    - Creates proxy with protocol type (http/socks5), host, port, and optional credentials
    """
    try:
        proxy = proxy_service.create_proxy(db, data)
        return proxy
    except Exception as e:
        logger.error(f"Failed to create proxy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create proxy",
        )


@router.put("/{proxy_id}", response_model=ProxyResponse)
def update_proxy(
    proxy_id: int,
    data: ProxyUpdate,
    db: Session = Depends(get_db),
):
    """
    Update a proxy.
    
    **Validates: Requirements 4.1**
    
    - Updates proxy configuration
    - Returns 404 if proxy not found
    """
    try:
        proxy = proxy_service.update_proxy(db, proxy_id, data)
        if not proxy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Proxy {proxy_id} not found",
            )
        return proxy
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update proxy {proxy_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update proxy",
        )


@router.delete("/{proxy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_proxy(proxy_id: int, db: Session = Depends(get_db)):
    """
    Delete a proxy.
    
    **Validates: Requirements 4.1**
    
    - Deletes proxy configuration
    - Returns 404 if proxy not found
    """
    try:
        success = proxy_service.delete_proxy(db, proxy_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Proxy {proxy_id} not found",
            )
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete proxy {proxy_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete proxy",
        )


@router.post("/{proxy_id}/test", response_model=ProxyTestResult)
async def test_proxy(proxy_id: int, db: Session = Depends(get_db)):
    """
    Test proxy connectivity.
    
    **Validates: Requirements 4.2, 4.3**
    
    - Tests proxy by making request to TikTok with 30s timeout (4.2)
    - Updates last_tested_at, is_working (via last_test_result), and response_time fields (4.3)
    - Returns test result with success status, response time, and error message if failed
    - Returns 404 if proxy not found
    """
    try:
        result = await proxy_service.test_proxy(db, proxy_id)
        if not result.success and result.error == "Proxy not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Proxy {proxy_id} not found",
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test proxy {proxy_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to test proxy",
        )
