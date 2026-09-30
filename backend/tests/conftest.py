"""pytest 基础设施：内存 SQLite 测试库 + 客户端 + 用户/权限 fixtures。"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.device import Device, DeviceLog  # noqa: F401  确保建表
from app.models.proxy_node import ProxyNode
from app.models.team import (
    Department, OperationLog, Role, RolePermission, User, UserRole,
)

import app.middleware.operation_log as op_log_module


@pytest.fixture(scope="session")
def engine():
    from sqlalchemy import event
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, record):  # noqa: ANN001
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture(scope="session")
def session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _patch_middleware_db(session_factory, monkeypatch):
    """操作日志中间件写入测试库（其内部直接用模块级 SessionLocal）。"""
    monkeypatch.setattr(op_log_module, "SessionLocal", session_factory)


@pytest.fixture()
def db(session_factory):
    session = session_factory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture(autouse=True)
def clean_tables(db):
    """每个测试后清空业务表，保证用例隔离。"""
    yield
    for model in (
        DeviceLog, Device, ProxyNode, OperationLog,
        UserRole, RolePermission, Role, User,
        Department,
    ):
        db.query(model).delete()
    db.commit()


@pytest.fixture()
def client(session_factory):
    """TestClient（不进 with：跳过 lifespan，避免触碰真实库与调度器）。"""

    def _get_db_override():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db_override
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def auth_headers(user: User) -> dict:
    token = create_access_token(
        {
            "sub": str(user.id),
            "username": user.username,
            "is_super_admin": user.is_super_admin,
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def super_admin(db) -> User:
    user = User(
        username="root",
        password_hash=hash_password("rootpass"),
        is_super_admin=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def normal_user(db) -> User:
    user = User(
        username="alice",
        password_hash=hash_password("alicepass"),
        real_name="Alice",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    role = Role(name="设备操作员", data_scope="self")
    db.add(role)
    db.commit()
    db.refresh(role)
    for perm in ("device:view", "device:manage"):
        db.add(RolePermission(role_id=role.id, permission=perm))
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    return user


@pytest.fixture()
def other_user(db) -> User:
    user = User(
        username="bob",
        password_hash=hash_password("bobpass"),
        real_name="Bob",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def make_node(db):
    def _make(status: str = "idle", **kw) -> ProxyNode:
        node = ProxyNode(
            ip=kw.get("ip", "1.2.3.4"),
            port=kw.get("port", 1080),
            username=kw.get("username"),
            password=kw.get("password"),
            protocol=kw.get("protocol", "socks5"),
            relay_ip=kw.get("relay_ip"),
            relay_port=kw.get("relay_port"),
            relay_protocol=kw.get("relay_protocol"),
            status=status,
        )
        db.add(node)
        db.commit()
        db.refresh(node)
        return node

    return _make
