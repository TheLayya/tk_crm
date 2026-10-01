import asyncio

import pytest
from starlette.requests import Request

from app.middleware.operation_log import OperationLogMiddleware
from app.models.team import OperationLog


def test_unhandled_exception_does_not_leak_sensitive_text_into_audit_log(db):
    secret = "private-card-key-and-password"
    request = Request({
        "type": "http", "method": "POST", "path": "/api/card-keys/1/import",
        "headers": [], "query_string": b"", "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345), "scheme": "http",
    })

    async def failing_request(request):
        raise RuntimeError(secret)

    middleware = OperationLogMiddleware(app=None)
    with pytest.raises(RuntimeError, match=secret):
        asyncio.run(middleware.dispatch(request, failing_request))

    log = db.query(OperationLog).filter(OperationLog.action == "IMPORT").one()
    assert log.result == "failed"
    assert log.error == "内部错误"
    assert secret not in f"{log.summary} {log.error}"
