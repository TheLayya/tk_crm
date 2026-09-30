import pytest

from app.models.device import Device, DeviceLog
from app.models.op_account import OpAccount, OpAuditLog
from app.schemas.op_account import OpAccountCreate, OpAccountUpdate
from app.services.op_account_service import create_op_account, update_op_account
from app.services.relation_history_service import relation_overview, readable_account_log
from tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def clean_accounts(db, clean_tables):
    yield
    db.rollback()
    for model in (OpAuditLog, OpAccount):
        db.query(model).delete()
    db.commit()


def test_relation_history_preserves_ban_snapshot_and_readable_changes(db, super_admin, make_node):
    first = make_node(ip="1.1.1.1")
    second = make_node(ip="2.2.2.2")
    account = create_op_account(db, OpAccountCreate(platform="tiktok", account="history-test", node_id=first.id), "root")
    update_op_account(db, account.id, OpAccountUpdate(status="封禁"), "root")
    update_op_account(db, account.id, OpAccountUpdate(node_id=second.id), "root")
    result = relation_overview(db, "account", account.id, super_admin)
    assert result["counts"]["node"] == 2
    assert result["ban_snapshots"][0]["nodes"] == ["1.1.1.1:1080"]
    assert result["current"][0]["nodes"][0]["id"] == second.id
    assert {item["id"]: item["current"] for item in result["history"]} == {first.id: False, second.id: True}
    log = db.query(OpAuditLog).filter(OpAuditLog.op_account_id == account.id, OpAuditLog.field_name == "node_id", OpAuditLog.old_value == str(first.id)).one()
    assert readable_account_log(db, log)["details"] == ["1.1.1.1:1080 → 2.2.2.2:1080"]


def test_ban_snapshot_uses_relation_saved_in_same_update(db, super_admin, make_node):
    first = make_node(ip="5.5.5.5")
    second = make_node(ip="6.6.6.6")
    account = create_op_account(db, OpAccountCreate(platform="tiktok", account="same-update", node_id=first.id), "root")
    update_op_account(db, account.id, OpAccountUpdate(status="封禁", node_id=second.id), "root")
    result = relation_overview(db, "account", account.id, super_admin)
    assert result["ban_snapshots"][0]["nodes"] == ["6.6.6.6:1080"]


def test_device_node_history_without_accounts_and_api_routes(client, db, super_admin, make_node):
    first = make_node(ip="3.3.3.3")
    second = make_node(ip="4.4.4.4")
    device = Device(name="天05", device_type="phone", owner_id=super_admin.id, node_id=second.id, node_ids=[second.id])
    db.add(device)
    db.flush()
    db.add(DeviceLog(device_id=device.id, user_id=super_admin.id, username="root", action="UPDATE", changes='{"node_id":{"old":"' + str(first.id) + '","new":"' + str(second.id) + '"}}'))
    db.commit()
    headers = auth_headers(super_admin)
    result = client.get(f"/api/devices/{device.id}/association-history", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["counts"]["node"] == 2
    result = client.get(f"/api/proxy-nodes/{first.id}/association-history", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["counts"]["device"] == 1
    assert result.json()["history"][0]["current"] is False
