import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.monitor import MonitorProxy
from app.schemas.proxy import ProxyCreate, ProxyUpdate, ProxyTestResult
from app.services.scraper_service import scraper_service

logger = logging.getLogger(__name__)


def get_proxies(db: Session, skip: int = 0, limit: int = 100) -> List[MonitorProxy]:
    """获取代理列表"""
    return db.query(MonitorProxy).offset(skip).limit(limit).all()


def get_proxy(db: Session, proxy_id: int) -> Optional[MonitorProxy]:
    """根据ID获取代理"""
    return db.query(MonitorProxy).filter(MonitorProxy.id == proxy_id).first()


def create_proxy(db: Session, data: ProxyCreate) -> MonitorProxy:
    """创建新代理"""
    # 如果没有提供 name，自动生成
    if not data.name:
        if data.username:
            name = f"{data.username}@{data.host}:{data.port}"
        else:
            name = f"{data.host}:{data.port}"
    else:
        name = data.name
    
    proxy = MonitorProxy(
        name=name,
        proxy_type=data.proxy_type,
        host=data.host,
        port=data.port,
        username=data.username,
        password=data.password,
        is_active=data.is_active,
        is_global=data.is_global,
    )
    db.add(proxy)
    db.commit()
    db.refresh(proxy)
    logger.info(f"Created proxy id={proxy.id} name={proxy.name}")
    return proxy


def update_proxy(db: Session, proxy_id: int, data: ProxyUpdate) -> Optional[MonitorProxy]:
    """更新代理信息"""
    proxy = get_proxy(db, proxy_id)
    if not proxy:
        return None

    update_data = data.model_dump(exclude_unset=True)
    
    # 如果更新了 host、port 或 username，且没有提供新的 name，则自动生成
    if ('host' in update_data or 'port' in update_data or 'username' in update_data) and 'name' not in update_data:
        host = update_data.get('host', proxy.host)
        port = update_data.get('port', proxy.port)
        username = update_data.get('username', proxy.username)
        
        if username:
            update_data['name'] = f"{username}@{host}:{port}"
        else:
            update_data['name'] = f"{host}:{port}"
    
    for field, value in update_data.items():
        setattr(proxy, field, value)

    proxy.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(proxy)
    logger.info(f"Updated proxy id={proxy_id}")
    return proxy


def delete_proxy(db: Session, proxy_id: int) -> bool:
    """删除代理，返回是否成功"""
    proxy = get_proxy(db, proxy_id)
    if not proxy:
        return False

    db.delete(proxy)
    db.commit()
    logger.info(f"Deleted proxy id={proxy_id}")
    return True


async def test_proxy(db: Session, proxy_id: int) -> ProxyTestResult:
    """
    测试指定代理的连通性。
    更新代理的 last_test_at / last_test_result / success_count / fail_count。
    返回 ProxyTestResult。
    """
    proxy = get_proxy(db, proxy_id)
    if not proxy:
        return ProxyTestResult(success=False, response_time=None, error="Proxy not found")

    result = await scraper_service.test_proxy(proxy)

    # 更新测试状态
    proxy.last_test_at = datetime.utcnow()
    proxy.last_test_result = "success" if result['success'] else "failed"
    if result['success']:
        proxy.success_count = (proxy.success_count or 0) + 1
    else:
        proxy.fail_count = (proxy.fail_count or 0) + 1
    proxy.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(proxy)

    logger.info(
        f"Tested proxy id={proxy_id}: success={result['success']}, "
        f"response_time={result.get('response_time')}"
    )

    return ProxyTestResult(
        success=result['success'],
        response_time=result.get('response_time'),
        error=result.get('error'),
    )
