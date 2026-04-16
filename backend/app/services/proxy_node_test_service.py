import asyncio
import logging
import time
from datetime import datetime
from typing import List, Optional

import httpx
from sqlalchemy.orm import Session

from app.models.proxy_node import ProxyNode
from app.schemas.proxy_node import ProxyNodeBatchTestResult, ProxyNodeTestResult

logger = logging.getLogger(__name__)

# 测试目标 URL
_TEST_URL = "http://httpbin.org/ip"
# 请求超时（秒）
_TIMEOUT = 15.0
# 批量测试最大并发数
_MAX_CONCURRENCY = 10


def _build_proxy_url(node: ProxyNode) -> str:
    """
    根据节点信息构建代理 URL。
    - 当 relay_ip 和 relay_port 均不为空时，优先使用中转地址
    - 否则使用原始地址（ip + port）
    """
    use_relay = bool(node.relay_ip and node.relay_port)

    if use_relay:
        protocol = node.relay_protocol or "http"
        ip = node.relay_ip
        port = node.relay_port
    else:
        protocol = node.protocol or "socks5"
        ip = node.ip
        port = node.port

    # 构建认证部分（仅原始节点有 username/password）
    if node.username and node.password:
        auth = f"{node.username}:{node.password}@"
    else:
        auth = ""

    return f"{protocol}://{auth}{ip}:{port}"


async def _do_test(node: ProxyNode) -> dict:
    """
    通过代理发起 HTTP 请求，测试节点连通性。

    返回：
      成功：{"success": True, "latency_ms": int}
      失败：{"success": False, "latency_ms": None, "error": str}
    """
    proxy_url = _build_proxy_url(node)
    logger.debug(f"Testing node id={node.id} via proxy={proxy_url}")

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(
            proxy=proxy_url,
            timeout=_TIMEOUT,
            follow_redirects=True,
        ) as client:
            response = await client.get(_TEST_URL)
            response.raise_for_status()

        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.debug(f"Node id={node.id} test succeeded, latency={elapsed_ms}ms")
        return {"success": True, "latency_ms": elapsed_ms}

    except Exception as exc:
        error_msg = str(exc)[:200]
        logger.debug(f"Node id={node.id} test failed: {error_msg}")
        return {"success": False, "latency_ms": None, "error": error_msg}


async def test_node(db: Session, node_id: int) -> Optional[ProxyNodeTestResult]:
    """
    测试单个节点连通性，更新数据库中的测试结果字段。

    节点不存在时返回 None。
    """
    node: Optional[ProxyNode] = db.query(ProxyNode).filter(ProxyNode.id == node_id).first()
    if not node:
        logger.warning(f"test_node: node id={node_id} not found")
        return None

    result = await _do_test(node)

    # 更新数据库字段
    node.last_test_result = "success" if result["success"] else "failed"
    node.last_test_latency = result.get("latency_ms")
    node.last_test_at = datetime.utcnow()
    db.commit()
    db.refresh(node)

    logger.info(
        f"test_node: node id={node_id} result={node.last_test_result} "
        f"latency={node.last_test_latency}ms"
    )

    return ProxyNodeTestResult(
        node_id=node_id,
        success=result["success"],
        latency_ms=result.get("latency_ms"),
        error=result.get("error"),
    )


async def batch_test_nodes(
    db: Session, node_ids: List[int]
) -> ProxyNodeBatchTestResult:
    """
    并发测试多个节点，使用 Semaphore 限制最大并发数为 10。

    返回 ProxyNodeBatchTestResult，包含 success_count、fail_count 和 results 列表。
    """
    semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def _test_with_semaphore(node_id: int) -> ProxyNodeTestResult:
        async with semaphore:
            result = await test_node(db, node_id)
            if result is None:
                # 节点不存在，视为失败
                return ProxyNodeTestResult(
                    node_id=node_id,
                    success=False,
                    latency_ms=None,
                    error="节点不存在",
                )
            return result

    results = await asyncio.gather(
        *[_test_with_semaphore(node_id) for node_id in node_ids]
    )

    success_count = sum(1 for r in results if r.success)
    fail_count = len(results) - success_count

    logger.info(
        f"batch_test_nodes: total={len(node_ids)}, "
        f"success={success_count}, fail={fail_count}"
    )

    return ProxyNodeBatchTestResult(
        success_count=success_count,
        fail_count=fail_count,
        results=list(results),
    )
