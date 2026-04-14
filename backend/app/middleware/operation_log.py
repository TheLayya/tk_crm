import re
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.core.database import SessionLocal
from app.core.security import decode_access_token
from app.models.team import OperationLog

# Path → (module, action) mapping
PATH_MODULE_MAP = [
    (r"POST /api/auth/login", None),  # skip login
    (r"GET /api/op-accounts/export", ("运营账号", "EXPORT")),
    (r"POST /api/op-accounts/import", ("运营账号", "CREATE")),
    (r"POST /api/op-accounts/collect", ("运营账号", "CREATE")),
    (r"POST /api/op-accounts", ("运营账号", "CREATE")),
    (r"PUT /api/op-accounts/\d+", ("运营账号", "UPDATE")),
    (r"DELETE /api/op-accounts/\d+", ("运营账号", "DELETE")),
    (r"POST /api/team/dept", ("部门管理", "CREATE")),
    (r"PUT /api/team/dept/\d+", ("部门管理", "UPDATE")),
    (r"DELETE /api/team/dept/\d+", ("部门管理", "DELETE")),
    (r"POST /api/team/member", ("成员管理", "CREATE")),
    (r"PUT /api/team/member/\d+", ("成员管理", "UPDATE")),
    (r"DELETE /api/team/member/\d+", ("成员管理", "DELETE")),
    (r"POST /api/team/member/\d+/reset-password", ("成员管理", "UPDATE")),
    (r"POST /api/team/role", ("角色管理", "CREATE")),
    (r"PUT /api/team/role/\d+", ("角色管理", "UPDATE")),
    (r"DELETE /api/team/role/\d+", ("角色管理", "DELETE")),
    (r"PUT /api/settings", ("系统设置", "UPDATE")),
]


class OperationLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        path = request.url.path

        # Only intercept write methods and export
        if method not in ("POST", "PUT", "DELETE") and not (method == "GET" and "export" in path):
            return await call_next(request)

        # Find matching module/action
        key = f"{method} {path}"
        module_action = None
        for pattern, mapping in PATH_MODULE_MAP:
            if re.fullmatch(pattern, key):
                module_action = mapping
                break

        # Skip if no mapping or explicitly None (like login)
        if module_action is None:
            return await call_next(request)

        module, action = module_action

        # Extract username from JWT
        username = "anonymous"
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            payload = decode_access_token(token)
            if payload:
                username = payload.get("username", "anonymous")

        # Get client IP
        ip = request.client.host if request.client else "unknown"

        # Execute request
        result = "success"
        error = None
        response = None
        try:
            response = await call_next(request)
            if response.status_code >= 400:
                result = "failed"
                error = f"HTTP {response.status_code}"
        except Exception as e:
            result = "failed"
            error = str(e)[:512]
            raise
        finally:
            # Record operation log
            db = SessionLocal()
            try:
                log = OperationLog(
                    username=username,
                    ip_address=ip,
                    module=module,
                    action=action,
                    summary=f"{action} {path}",
                    result=result,
                    error=error,
                )
                db.add(log)
                db.commit()
            except Exception:
                pass
            finally:
                db.close()

        return response
