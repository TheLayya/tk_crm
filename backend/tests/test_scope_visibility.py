"""API regressions for terminal-derived account and node ownership."""
import csv
import io
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.models.device import Device
from app.models.op_account import EmailAccount, EmailAccountRelation, OpAccount, OpAuditLog, OpCollectTask
from app.models.proxy_node import ProxyNode
from app.models.team import Department, OperationLog, Role, RolePermission, User, UserRole
from app.models.video import OpAccountVideo
from app.services import op_account_service
from tests.conftest import auth_headers


PERMISSIONS = (
    "op_account:view", "op_account:collect", "op_account:export", "op_account:edit",
    "op_account:delete", "op_account:create", "proxy_node:view", "proxy_node:manage",
    "email:view", "device:view", "device:manage",
)


def grant(db, user, scope):
    role = Role(name=f"scope-{user.username}-{scope}", data_scope=scope)
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.add_all(RolePermission(role_id=role.id, permission=permission) for permission in PERMISSIONS)
    db.commit()


@pytest.fixture(autouse=True)
def isolated_collection(db, session_factory, monkeypatch, clean_tables):
    """Keep collection in memory; delete children before global FK cleanup."""
    def clean():
        db.rollback()
        for model in (EmailAccountRelation, OpAccountVideo, OpAuditLog, OpCollectTask, OpAccount):
            db.query(model).delete(synchronize_session=False)
        db.commit()
        db.expunge_all()

    clean()
    scheduled = []
    monkeypatch.setattr(op_account_service, "SessionLocal", session_factory)
    monkeypatch.setattr(
        op_account_service, "run_collect_task",
        lambda task_id, account_ids: scheduled.append((task_id, account_ids)),
    )
    yield scheduled
    clean()


@pytest.fixture
def assets(db, normal_user, other_user):
    department, outside_department = Department(name="operations"), Department(name="outside")
    db.add_all([department, outside_department])
    db.flush()
    normal_user.department_id = other_user.department_id = department.id
    outsider = User(username="carol", password_hash=normal_user.password_hash,
                    department_id=outside_department.id, is_active=True)
    db.add(outsider)
    db.flush()
    nodes = {
        name: ProxyNode(ip=f"10.50.0.{index}", port=1080, protocol="socks5", status="idle",
                        purchase_price=index, created_by=normal_user.username if name == "creator" else None)
        for index, name in enumerate(
            ("primary", "secondary", "peer", "foreign", "deleted", "creator", "direct", "email"), 1,
        )
    }
    db.add_all(nodes.values())
    db.flush()
    devices = {
        "own": Device(name="own-phone", device_type="phone", owner_id=normal_user.id,
                      node_id=nodes["primary"].id, node_ids=[nodes["primary"].id, nodes["secondary"].id]),
        "peer": Device(name="peer-phone", device_type="phone", owner_id=other_user.id,
                       node_id=nodes["peer"].id),  # Legacy single-node terminal.
        "foreign": Device(name="foreign-phone", device_type="phone", owner_id=outsider.id,
                          node_id=nodes["foreign"].id),
        "deleted": Device(name="deleted-phone", device_type="phone", owner_id=normal_user.id,
                          node_id=nodes["deleted"].id, is_deleted=True),
    }
    db.add_all(devices.values())
    db.flush()
    accounts = {
        "own": OpAccount(platform="tiktok", account="own", device_id=devices["own"].id,
                         node_id=nodes["primary"].id, registrant=outsider.username, operator=outsider.username),
        "peer": OpAccount(platform="tiktok", account="peer", device_id=devices["peer"].id,
                          node_id=nodes["peer"].id, registrant=outsider.username),
        "foreign": OpAccount(platform="tiktok", account="foreign", device_id=devices["foreign"].id,
                             node_id=nodes["foreign"].id, registrant=outsider.username),
        "shared": OpAccount(platform="tiktok", account="shared", node_id=nodes["primary"].id,
                            registrant=outsider.username),
        "deleted": OpAccount(platform="tiktok", account="deleted", device_id=devices["deleted"].id,
                             node_id=nodes["deleted"].id),
        "registrant": OpAccount(platform="tiktok", account="registrant", registrant=normal_user.username,
                                node_id=nodes["direct"].id),
        "operator": OpAccount(platform="tiktok", account="operator", operator=normal_user.username),
        "dept": OpAccount(platform="tiktok", account="dept", registrant=other_user.username),
        "unassigned": OpAccount(platform="tiktok", account="unassigned"),
    }
    for index, account in enumerate(accounts.values(), 1):
        account.purchase_price = index
    db.add_all(accounts.values())
    db.flush()
    for account in accounts.values():
        db.add(OpAccountVideo(account_id=account.id, video_id=f"video-{account.account}", play_count=17))
        db.add(OpAuditLog(op_account_id=account.id, action="create", new_value=account.account,
                          operator=outsider.username))
    email = EmailAccount(email="alice@example.com", registrant=normal_user.username, node_id=nodes["email"].id)
    db.add(email)
    db.flush()
    db.add_all([
        EmailAccountRelation(email_id=email.id, op_account_id=accounts["own"].id),
        EmailAccountRelation(email_id=email.id, op_account_id=accounts["shared"].id),
        OperationLog(username=normal_user.username, module="节点管理", action="UPDATE",
                     summary=f"UPDATE /api/proxy-nodes/{nodes['primary'].id}", result="success"),
    ])
    db.commit()
    return {"nodes": nodes, "devices": devices, "accounts": accounts, "email": email}


def csv_rows(response):
    assert response.status_code == 200, response.text
    return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))


@pytest.mark.parametrize("scope", ["self", "dept", "all"])
def test_lists_stats_exports_options_and_overview_share_scope(client, db, normal_user, assets, scope):
    grant(db, normal_user, scope)
    headers = auth_headers(normal_user)
    account_names = {"own", "registrant", "operator"}
    node_names = {"primary", "secondary", "creator", "direct", "email"}
    device_names = {"own"}
    if scope == "dept":
        account_names |= {"peer", "dept"}
        node_names.add("peer")
        device_names.add("peer")
    elif scope == "all":
        account_names, node_names = set(assets["accounts"]), set(assets["nodes"])
        device_names |= {"peer", "foreign"}
    accounts = [assets["accounts"][name] for name in account_names]
    nodes = [assets["nodes"][name] for name in node_names]
    account_ids, node_ids = {account.id for account in accounts}, {node.id for node in nodes}

    response = client.get("/api/op-accounts", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == len(accounts)
    assert {row["id"] for row in response.json()["items"]} == account_ids
    stats = client.get("/api/op-accounts/stats", headers=headers).json()
    assert stats["total"] == len(accounts)
    assert stats["total_purchase_cost"] == sum(account.purchase_price for account in accounts)
    assert {row["account"] for row in csv_rows(client.get("/api/op-accounts/export", headers=headers))} == account_names
    assert client.get("/api/op-accounts", headers=headers, params={"keyword": "peer"}).json()["total"] == int(scope != "self")

    response = client.get("/api/proxy-nodes", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == len(nodes)
    assert {row["id"] for row in response.json()["items"]} == node_ids
    shared_node = next(row for row in response.json()["items"] if row["id"] == assets["nodes"]["primary"].id)
    expected_shared_ids = {assets["accounts"]["own"].id}
    if scope == "all":
        expected_shared_ids.add(assets["accounts"]["shared"].id)
    assert set(shared_node["account_ids"]) == expected_shared_ids
    assert {row["id"] for row in shared_node["accounts"]} == expected_shared_ids
    assert shared_node["account_count"] == len(expected_shared_ids)
    stats = client.get("/api/proxy-nodes/stats", headers=headers).json()
    assert stats["total"] == len(nodes)
    assert float(stats["total_purchase_cost"]) == sum(node.purchase_price for node in nodes)
    assert {row["ip"] for row in csv_rows(client.get("/api/proxy-nodes/export", headers=headers))} == {node.ip for node in nodes}
    options = client.get("/api/emails/account-options", headers=headers)
    assert options.status_code == 200, options.text
    assert {row["id"] for row in options.json()} == account_ids
    response = client.get("/api/overview", headers=headers)
    assert response.status_code == 200, response.text
    overview = response.json()
    assert overview["assets"]["accounts"]["total"] == len(accounts)
    assert overview["assets"]["nodes"]["total"] == len(nodes)
    assert {row["id"] for row in overview["device_rows"]} == {assets["devices"][name].id for name in device_names}
    own_device = next(row for row in overview["device_rows"] if row["id"] == assets["devices"]["own"].id)
    assert {row["id"] for row in own_device["accounts"]} == {assets["accounts"]["own"].id}
    assert {row["id"] for row in own_device["nodes"]} == {assets["nodes"][name].id for name in ("primary", "secondary")}


def test_owner_details_history_and_emails_exclude_shared_node_foreign_account(client, db, normal_user, assets):
    grant(db, normal_user, "self")
    headers = auth_headers(normal_user)
    own, foreign = assets["accounts"]["own"], assets["accounts"]["shared"]
    node = assets["nodes"]["primary"]
    videos = client.get(f"/api/op-accounts/{own.id}/videos", headers=headers)
    assert videos.status_code == 200, videos.text
    assert videos.json()["total"] == 1
    assert videos.json()["items"][0]["video_id"] == "video-own"
    logs = client.get(f"/api/op-accounts/{own.id}/logs", headers=headers)
    assert logs.status_code == 200, logs.text
    assert len(logs.json()) == 1
    assert logs.json()[0]["new_value"] == "own"
    history = client.get(f"/api/op-accounts/{own.id}/association-history", headers=headers)
    assert history.status_code == 200, history.text
    assert [row["account"] for row in history.json()["current"]] == ["own"]
    for suffix in ("/videos", "/logs", "/association-history"):
        assert client.get(f"/api/op-accounts/{foreign.id}{suffix}", headers=headers).status_code == 403
    history = client.get(f"/api/proxy-nodes/{node.id}/association-history", headers=headers)
    assert history.status_code == 200, history.text
    assert [row["account"] for row in history.json()["current"]] == ["own"]
    assert {row["id"] for row in history.json()["history"] if row["kind"] == "account"} == {own.id}
    logs = client.get(f"/api/proxy-nodes/{node.id}/logs", headers=headers)
    assert logs.status_code == 200, logs.text
    assert logs.json()["total"] == 1
    for suffix in ("", "/logs", "/association-history"):
        assert client.get(f"/api/proxy-nodes/{assets['nodes']['foreign'].id}{suffix}", headers=headers).status_code == 403
    emails = client.get(f"/api/emails/for-account/{own.id}", headers=headers)
    assert emails.status_code == 200, emails.text
    assert [row["email"] for row in emails.json()] == ["alice@example.com"]
    assert client.get(f"/api/emails/for-account/{foreign.id}", headers=headers).status_code == 404
    relations = client.get(f"/api/emails/{assets['email'].id}/relations", headers=headers)
    assert relations.status_code == 200, relations.text
    assert {row["op_account_id"] for row in relations.json()} == {own.id}


def test_deleted_terminal_revokes_only_terminal_inherited_visibility(client, db, normal_user, assets):
    grant(db, normal_user, "self")
    assets["devices"]["own"].is_deleted = True
    db.commit()
    headers = auth_headers(normal_user)
    own = assets["accounts"]["own"]
    listing = client.get("/api/op-accounts", headers=headers).json()
    assert {row["account"] for row in listing["items"]} == {"registrant", "operator"}
    assert client.get(f"/api/op-accounts/{own.id}/videos", headers=headers).status_code == 403
    listing = client.get("/api/proxy-nodes", headers=headers).json()
    assert {row["id"] for row in listing["items"]} == {assets["nodes"][name].id for name in ("creator", "direct", "email")}
    own.operator = normal_user.username
    db.commit()
    listing = client.get("/api/op-accounts", headers=headers).json()
    assert {row["account"] for row in listing["items"]} == {"own", "registrant", "operator"}
    assert client.get(f"/api/op-accounts/{own.id}/videos", headers=headers).status_code == 200


def test_collection_validates_entire_batch_and_records_requester(client, db, normal_user, assets, isolated_collection):
    grant(db, normal_user, "self")
    headers = auth_headers(normal_user)
    own, foreign = assets["accounts"]["own"], assets["accounts"]["shared"]
    for body in ({}, {"account_ids": []}, {"account_ids": "all"}, {"account_ids": [True]},
                 {"account_ids": [0]}, {"account_ids": [str(own.id)]}, {"account_ids": [1.5]}):
        assert client.post("/api/op-accounts/collect", headers=headers, json=body).status_code == 422
    assert client.post("/api/op-accounts/collect", headers=headers, json={"account_ids": [own.id, foreign.id]}).status_code == 403
    assert client.post("/api/op-accounts/collect", headers=headers, json={"account_ids": [own.id, 999999]}).status_code == 404
    assert db.query(OpCollectTask).count() == 0
    assert isolated_collection == []
    response = client.post("/api/op-accounts/collect", headers=headers, json={"account_ids": [own.id, own.id]})
    assert response.status_code == 200, response.text
    task_id = response.json()["task_id"]
    task = db.get(OpCollectTask, task_id)
    assert task.created_by == normal_user.username
    assert task.total == 1
    assert isolated_collection == [(task_id, [own.id])]
    assert client.get(f"/api/op-accounts/tasks/{task_id}", headers=headers).status_code == 200


@pytest.mark.parametrize("scope,allowed", [("self", {"alice"}), ("dept", {"alice", "bob"}), ("all", {"alice", "bob", "carol", None})])
def test_task_visibility_uses_requester_scope_and_restricts_legacy_null(client, db, normal_user, assets, scope, allowed):
    grant(db, normal_user, scope)
    headers = auth_headers(normal_user)
    for index, creator in enumerate(("alice", "bob", "carol", None)):
        db.add(OpCollectTask(id=f"scope-task-{index}", created_by=creator, status="completed",
                             total=1, completed=1, success=1, failed=0))
    db.commit()
    for index, creator in enumerate(("alice", "bob", "carol", None)):
        response = client.get(f"/api/op-accounts/tasks/scope-task-{index}", headers=headers)
        assert response.status_code == (200 if creator in allowed else 403), response.text
    assert client.get("/api/op-accounts/tasks/missing", headers=headers).status_code == 404


def test_owner_operations_allow_own_objects_and_reject_foreign(client, db, normal_user, assets):
    grant(db, normal_user, "self")
    headers = auth_headers(normal_user)
    own, foreign = assets["accounts"]["own"], assets["accounts"]["shared"]
    own_node, foreign_node = assets["nodes"]["primary"], assets["nodes"]["foreign"]
    response = client.put(f"/api/op-accounts/{own.id}", headers=headers, json={"remark": "owner update"})
    assert response.status_code == 200, response.text
    assert response.json()["remark"] == "owner update"
    assert client.put(f"/api/op-accounts/{foreign.id}", headers=headers, json={"remark": "forbidden"}).status_code == 403
    assert client.post("/api/op-accounts/batch-status", headers=headers, json={"ids": [own.id], "status": "自用"}).json() == {"updated": 1}
    assert client.post("/api/op-accounts/batch-status", headers=headers, json={"ids": [own.id, foreign.id], "status": "封禁"}).status_code == 403
    db.expire_all()
    assert db.get(OpAccount, own.id).status == "自用"
    assert db.get(OpAccount, foreign.id).remark is None
    response = client.patch(f"/api/proxy-nodes/{own_node.id}", headers=headers, json={"remark": "owner node"})
    assert response.status_code == 200, response.text
    assert response.json()["remark"] == "owner node"
    assert client.patch(f"/api/proxy-nodes/{foreign_node.id}", headers=headers, json={"remark": "forbidden"}).status_code == 403
    assert client.patch("/api/proxy-nodes/batch/status", headers=headers, json={"node_ids": [foreign_node.id], "status": "disabled"}).status_code == 403
    assert client.put(f"/api/proxy-nodes/{own_node.id}/relation", headers=headers, json={"account_id": foreign.id}).status_code == 403
    assert client.delete(f"/api/proxy-nodes/{own_node.id}", headers=headers).status_code == 403
    assert client.delete(f"/api/proxy-nodes/{foreign_node.id}", headers=headers).status_code == 403
    assert client.delete(f"/api/op-accounts/{foreign.id}", headers=headers).status_code == 403
    response = client.put(f"/api/proxy-nodes/{own_node.id}/relation", headers=headers, json={"account_id": own.id})
    assert response.status_code == 200, response.text
    assert client.delete(f"/api/op-accounts/{own.id}", headers=headers).status_code == 409
    assert client.delete(f"/api/op-accounts/{assets['accounts']['operator'].id}", headers=headers).status_code == 204
    db.expire_all()
    assert db.get(OpAccount, foreign.id) is not None


def test_owner_can_detach_terminal_nodes_and_delete_node_with_own_account(client, db, normal_user, assets):
    grant(db, normal_user, "self")
    headers = auth_headers(normal_user)
    response = client.put(f"/api/proxy-nodes/{assets['nodes']['secondary'].id}/relation", headers=headers, json={"device_id": None})
    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(Device, assets["devices"]["own"].id).node_ids == [assets["nodes"]["primary"].id]
    assets["accounts"]["shared"].node_id = None
    db.commit()
    response = client.delete(f"/api/proxy-nodes/{assets['nodes']['primary'].id}", headers=headers)
    assert response.status_code == 204, response.text
    db.expire_all()
    assert db.get(OpAccount, assets["accounts"]["own"].id).node_id is None
    assert db.get(Device, assets["devices"]["own"].id).node_ids == []


def test_account_relations_cannot_inject_foreign_terminal_or_node(client, db, normal_user, assets, isolated_collection):
    grant(db, normal_user, "self")
    headers = auth_headers(normal_user)
    own = assets["accounts"]["own"]
    for values in ({"device_id": assets["devices"]["foreign"].id}, {"node_id": assets["nodes"]["foreign"].id}):
        assert client.put(f"/api/op-accounts/{own.id}", headers=headers, json=values).status_code == 403
        response = client.post("/api/op-accounts", headers=headers,
                               json={"platform": "tiktok", "account": "injected", **values})
        assert response.status_code == 403, response.text
    assert db.query(OpAccount).filter_by(account="injected").count() == 0
    assert isolated_collection == []
    db.expire_all()
    assert db.get(OpAccount, own.id).device_id == assets["devices"]["own"].id


def test_shared_email_node_is_visible_but_cannot_delete_foreign_email_link(client, db, normal_user, assets):
    grant(db, normal_user, "self")
    headers = auth_headers(normal_user)
    node = assets["nodes"]["email"]
    foreign_email = EmailAccount(email="carol@example.com", registrant="carol", node_id=node.id)
    db.add(foreign_email)
    db.commit()
    assert client.get(f"/api/proxy-nodes/{node.id}", headers=headers).status_code == 200
    assert client.delete(f"/api/proxy-nodes/{node.id}", headers=headers).status_code == 403
    assert client.request("DELETE", "/api/proxy-nodes/batch", headers=headers, json={"node_ids": [node.id]}).status_code == 403
    db.expire_all()
    assert db.get(ProxyNode, node.id) is not None
    assert db.get(EmailAccount, foreign_email.id).node_id == node.id
    assert db.get(EmailAccount, assets["email"].id).node_id == node.id


def test_legacy_device_create_and_update_cannot_attach_foreign_node(client, db, normal_user, assets):
    grant(db, normal_user, "self")
    headers = auth_headers(normal_user)
    foreign_node = assets["nodes"]["foreign"]
    own_device = assets["devices"]["own"]
    response = client.post("/api/devices", headers=headers,
                           json={"name": "injected-phone", "device_type": "phone", "node_id": foreign_node.id})
    assert response.status_code == 403, response.text
    response = client.patch(f"/api/devices/{own_device.id}", headers=headers, json={"node_id": foreign_node.id})
    assert response.status_code == 403, response.text
    db.expire_all()
    assert db.query(Device).filter_by(name="injected-phone").count() == 0
    assert db.get(Device, own_device.id).node_id == assets["nodes"]["primary"].id


def test_collect_task_owner_migration_preserves_legacy_tasks(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    configuration = Config(str(backend / "alembic.ini"))
    configuration.set_main_option("script_location", str(backend / "alembic"))
    database_url = "sqlite:///" + (tmp_path / "task-owner.db").as_posix()
    configuration.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(configuration, "20261006_0022")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO op_collect_tasks (id, status, total, completed, success, failed, created_at, updated_at) "
                "VALUES ('legacy-task', 'completed', 1, 1, 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))
        command.upgrade(configuration, "20261006_0023")
        owner = next(column for column in inspect(engine).get_columns("op_collect_tasks") if column["name"] == "created_by")
        assert owner["nullable"] is True
        with engine.begin() as connection:
            assert connection.execute(text("SELECT created_by FROM op_collect_tasks WHERE id='legacy-task'")).scalar_one() is None
            connection.execute(text("UPDATE op_collect_tasks SET created_by='alice' WHERE id='legacy-task'"))
        command.upgrade(configuration, "20261006_0023")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT created_by FROM op_collect_tasks WHERE id='legacy-task'")).scalar_one() == "alice"
    finally:
        engine.dispose()
