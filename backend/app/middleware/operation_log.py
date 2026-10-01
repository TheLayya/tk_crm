import re
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.core.database import SessionLocal
from app.core.security import decode_access_token
from app.models.team import OperationLog

# Path → (module, action) mapping
PATH_MODULE_MAP = [
    (r"POST /api/card-keys/\d+/import", ("卡密管理", "IMPORT")),
    (r"POST /api/card-keys/\d+/claim", ("卡密管理", "CLAIM")),
    (r"POST /api/card-keys/\d+/keys/\d+/consume", ("卡密管理", "CONSUME")),
    (r"POST /api/card-keys/\d+/keys/\d+/release", ("卡密管理", "RELEASE")),
    (r"POST /api/card-keys", ("卡密管理", "CREATE")),
    (r"PUT /api/card-keys/\d+", ("卡密管理", "UPDATE")),
    (r"POST /api/emails", ("邮箱管理", "CREATE")),
    (r"POST /api/emails/import", ("邮箱管理", "CREATE")),
    (r"POST /api/emails/check", ("邮箱管理", "UPDATE")),
    (r"PUT /api/emails/\d+", ("邮箱管理", "UPDATE")),
    (r"DELETE /api/emails/\d+", ("邮箱管理", "DELETE")),
    (r"POST /api/emails/\d+/relations", ("邮箱关联", "CREATE")),
    (r"DELETE /api/emails/\d+/relations/\d+", ("邮箱关联", "UPDATE")),
    (r"POST /api/auth/login", None),  # skip login
    (r"GET /api/proxy-nodes/\d+/uri", ("节点管理", "VIEW_SECRET")),  # 节点二维码 URI（含凭据，审计）
    (r"POST /api/devices", ("终端资产", "CREATE")),
    (r"PATCH /api/devices/\d+", ("终端资产", "UPDATE")),
    (r"PUT /api/devices/\d+/relations", ("终端关联", "UPDATE")),
    (r"DELETE /api/devices/\d+", ("终端资产", "DELETE")),
    (r"GET /api/op-accounts/export", ("运营账号", "EXPORT")),
    (r"POST /api/op-accounts/import", ("运营账号", "CREATE")),
    (r"POST /api/op-accounts/collect", ("运营账号", "CREATE")),
    (r"POST /api/op-accounts/batch-assign", ("运营账号", "UPDATE")),
    (r"POST /api/op-accounts", ("运营账号", "CREATE")),
    (r"PUT /api/op-accounts/\d+", ("运营账号", "UPDATE")),
    (r"PUT /api/proxy-nodes/\d+/relation", ("节点关联", "UPDATE")),
    (r"POST /api/proxy-nodes", ("节点管理", "CREATE")),
    (r"PATCH /api/proxy-nodes/\d+", ("节点管理", "UPDATE")),
    (r"DELETE /api/proxy-nodes/\d+", ("节点管理", "DELETE")),
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
    (r"PUT /api/work-items/categories", ("备忘大类", "UPDATE")),
    (r"POST /api/work-items", ("备忘管理", "CREATE")),
    (r"PUT /api/work-items/\d+", ("备忘管理", "UPDATE")),
    (r"DELETE /api/work-items/\d+", ("备忘管理", "DELETE")),
]


class OperationLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        path = request.url.path

        # Only intercept write methods, export and URI (credential view)
        if method not in ("POST", "PATCH", "PUT", "DELETE") and not (
            method == "GET" and ("export" in path or "/uri" in path)
        ):
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
        except Exception:
            result = "failed"
            error = "内部错误"
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
