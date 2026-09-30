"""终端资产（设备）API 测试：CRUD、越权矩阵、数据范围、节点绑定、软删除、审计。"""
import json

from app.models.device import Device, DeviceLog
from app.models.proxy_node import ProxyNode
from app.models.op_account import OpAccount
from app.models.team import OperationLog

from .conftest import auth_headers


def _create_payload(**kw) -> dict:
    payload = {"name": "01 测试机", "device_type": "pc", **kw}
    return payload


# ---------------------------------------------------------------------------
# CRUD 主流程（超管）
# ---------------------------------------------------------------------------

def test_create_and_get_device(client, db, super_admin):
    headers = auth_headers(super_admin)
    resp = client.post("/api/devices", json=_create_payload(owner_id=super_admin.id), headers=headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "01 测试机"
    assert data["owner_name"] == "root"
    assert data["node_id"] is None
    assert data["node_ip"] is None

    device_id = data["id"]
    resp = client.get(f"/api/devices/{device_id}", headers=headers)
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["node"] is None  # 未绑定设备详情 node 摘要为 null

    resp = client.get("/api/devices", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_update_and_delete_flow(client, db, super_admin):
    headers = auth_headers(super_admin)
    resp = client.post("/api/devices", json=_create_payload(owner_id=super_admin.id), headers=headers)
    device_id = resp.json()["id"]

    resp = client.patch(
        f"/api/devices/{device_id}",
        json={"name": "改名机", "remark": "备注"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "改名机"
    assert resp.json()["remark"] == "备注"

    # PATCH 保留相同 node_id 不误判 409（唯一性预检查排除自身）
    resp = client.patch(f"/api/devices/{device_id}", json={"name": "改名机"}, headers=headers)
    assert resp.status_code == 200

    resp = client.delete(f"/api/devices/{device_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # 软删除后不可见
    assert client.get(f"/api/devices/{device_id}", headers=headers).status_code == 404
    assert client.get("/api/devices", headers=headers).json()["total"] == 0

    # 软删除后 logs 仍可查（超管）
    resp = client.get(f"/api/devices/{device_id}/logs", headers=headers)
    assert resp.status_code == 200
    actions = [item["action"] for item in resp.json()["items"]]
    assert actions == ["DELETE", "UPDATE", "CREATE"]


def test_patch_deleted_device_returns_404(client, db, super_admin):
    headers = auth_headers(super_admin)
    resp = client.post("/api/devices", json=_create_payload(owner_id=super_admin.id), headers=headers)
    device_id = resp.json()["id"]
    client.delete(f"/api/devices/{device_id}", headers=headers)

    assert client.patch(f"/api/devices/{device_id}", json={"name": "x"}, headers=headers).status_code == 404
    assert client.delete(f"/api/devices/{device_id}", headers=headers).status_code == 404


# ---------------------------------------------------------------------------
# 越权矩阵（非超管）
# ---------------------------------------------------------------------------

def test_non_admin_scope_and_idor(client, db, normal_user, other_user, super_admin):
    my_headers = auth_headers(normal_user)
    # 超管为 alice 与 bob 各建一台设备
    resp = client.post("/api/devices", json=_create_payload(owner_id=normal_user.id), headers=auth_headers(super_admin))
    mine = resp.json()["id"]
    resp = client.post("/api/devices", json=_create_payload(name="bob 的", owner_id=other_user.id), headers=auth_headers(super_admin))
    others = resp.json()["id"]

    # list 数据范围：仅见自己
    resp = client.get("/api/devices", headers=my_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["id"] == mine

    # owner_id 筛选参数被忽略
    resp = client.get(f"/api/devices?owner_id={other_user.id}", headers=my_headers)
    assert resp.json()["total"] == 1

    # get / patch / delete / logs 他人设备 → 403
    assert client.get(f"/api/devices/{others}", headers=my_headers).status_code == 403
    assert client.patch(f"/api/devices/{others}", json={"name": "x"}, headers=my_headers).status_code == 403
    assert client.delete(f"/api/devices/{others}", headers=my_headers).status_code == 403
    assert client.get(f"/api/devices/{others}/logs", headers=my_headers).status_code == 404

    # create 指定他人 owner → 400
    resp = client.post(
        "/api/devices",
        json=_create_payload(owner_id=other_user.id),
        headers=my_headers,
    )
    assert resp.status_code == 400

    # create 不传 owner → 强制为自己
    resp = client.post("/api/devices", json=_create_payload(name="自己的"), headers=my_headers)
    assert resp.status_code == 201
    assert resp.json()["owner_id"] == normal_user.id

    # patch 改 owner → 400
    resp = client.patch(f"/api/devices/{mine}", json={"owner_id": other_user.id}, headers=my_headers)
    assert resp.status_code == 400


def test_non_admin_update_owner_null_400(client, db, normal_user, super_admin):
    resp = client.post(
        "/api/devices",
        json=_create_payload(owner_id=normal_user.id),
        headers=auth_headers(super_admin),
    )
    device_id = resp.json()["id"]
    resp = client.patch(
        f"/api/devices/{device_id}",
        json={"owner_id": None},
        headers=auth_headers(normal_user),
    )
    assert resp.status_code == 400


def test_validation_errors(client, db, super_admin):
    headers = auth_headers(super_admin)
    # device_type 非法
    resp = client.post(
        "/api/devices",
        json=_create_payload(device_type="tablet", owner_id=super_admin.id),
        headers=headers,
    )
    assert resp.status_code == 422
    # name 为空
    resp = client.post(
        "/api/devices",
        json=_create_payload(name="", owner_id=super_admin.id),
        headers=headers,
    )
    assert resp.status_code == 422
    # name 显式 null
    resp = client.post(
        "/api/devices",
        json=_create_payload(owner_id=super_admin.id) | {"name": None},
        headers=headers,
    )
    assert resp.status_code == 422

    resp = client.post("/api/devices", json=_create_payload(owner_id=super_admin.id), headers=headers)
    device_id = resp.json()["id"]
    # PATCH name 显式 null → 400
    resp = client.patch(f"/api/devices/{device_id}", json={"name": None}, headers=headers)
    assert resp.status_code == 400
    # PATCH device_type 显式 null → 400
    resp = client.patch(f"/api/devices/{device_id}", json={"device_type": None}, headers=headers)
    assert resp.status_code == 400
    # PATCH 未知字段 → 422（schema extra=forbid 直接拒绝）
    resp = client.patch(f"/api/devices/{device_id}", json={"hack_field": "x"}, headers=headers)
    assert resp.status_code == 422
    # PATCH 保留字段 → 422（防 is_deleted 注入）
    resp = client.patch(f"/api/devices/{device_id}", json={"is_deleted": True}, headers=headers)
    assert resp.status_code == 422
    # 确认设备未被篡改
    assert client.get(f"/api/devices/{device_id}", headers=headers).status_code == 200


def test_bindable_nodes_exclude_ownership(client, db, super_admin, normal_user, other_user):
    """非超管借 exclude_device_id 探测他人设备绑定 → 403。"""
    # 超管为 bob 建一台绑定节点的设备
    bound_node = ProxyNode(ip="5.5.5.5", port=1080, protocol="socks5", status="idle")
    db.add(bound_node)
    db.commit()
    db.refresh(bound_node)
    resp = client.post(
        "/api/devices",
        json=_create_payload(name="bob 绑定机", owner_id=other_user.id, node_id=bound_node.id),
        headers=auth_headers(super_admin),
    )
    others_device = resp.json()["id"]

    # 非超管传他人设备 ID → 403
    resp = client.get(
        f"/api/devices/bindable-nodes?exclude_device_id={others_device}",
        headers=auth_headers(normal_user),
    )
    assert resp.status_code == 403

    # 非超管传自己设备 ID → 200
    resp = client.post(
        "/api/devices",
        json=_create_payload(owner_id=normal_user.id),
        headers=auth_headers(super_admin),
    )
    mine = resp.json()["id"]
    resp = client.get(
        f"/api/devices/bindable-nodes?exclude_device_id={mine}",
        headers=auth_headers(normal_user),
    )
    assert resp.status_code == 200


def test_permission_denied_without_device_perms(client, db, normal_user, super_admin):
    from app.models.team import UserRole
    # 移除 alice 的全部角色 → 无 device 权限
    db.query(UserRole).filter(UserRole.user_id == normal_user.id).delete()
    db.commit()
    headers = auth_headers(normal_user)
    assert client.get("/api/devices", headers=headers).status_code == 403
    assert client.post("/api/devices", json=_create_payload(), headers=headers).status_code == 403


# ---------------------------------------------------------------------------
# 节点绑定
# ---------------------------------------------------------------------------

def test_bind_node_rules(client, db, super_admin, make_node):
    headers = auth_headers(super_admin)
    node = make_node(status="idle")

    resp = client.post(
        "/api/devices",
        json=_create_payload(owner_id=super_admin.id, node_id=node.id),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["node_id"] == node.id
    assert resp.json()["node_ip"] == "1.2.3.4:1080"
    device_id = resp.json()["id"]

    # 节点支持被第二台设备共享
    resp = client.post(
        "/api/devices",
        json=_create_payload(name="第二台", owner_id=super_admin.id, node_id=node.id),
        headers=headers,
    )
    assert resp.status_code == 201

    # 保留原节点 PATCH 不误判 409
    resp = client.patch(f"/api/devices/{device_id}", json={"remark": "x"}, headers=headers)
    assert resp.status_code == 200

    # 解绑
    resp = client.patch(f"/api/devices/{device_id}", json={"node_id": None}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["node_id"] is None

    # 解绑后节点可再绑
    resp = client.post(
        "/api/devices",
        json=_create_payload(name="第三台", owner_id=super_admin.id, node_id=node.id),
        headers=headers,
    )
    assert resp.status_code == 201


def test_bind_node_not_found_and_bad_status(client, db, super_admin, make_node):
    headers = auth_headers(super_admin)
    # 不存在
    resp = client.post(
        "/api/devices",
        json=_create_payload(owner_id=super_admin.id, node_id=99999),
        headers=headers,
    )
    assert resp.status_code == 404

    for status in ("sold", "disabled"):
        node = make_node(status=status)
        resp = client.post(
            "/api/devices",
            json=_create_payload(owner_id=super_admin.id, node_id=node.id),
            headers=headers,
        )
        assert resp.status_code == 400, f"{status}: {resp.text}"


def test_soft_delete_frees_node(client, db, super_admin, make_node):
    headers = auth_headers(super_admin)
    node = make_node(status="idle")
    resp = client.post(
        "/api/devices",
        json=_create_payload(owner_id=super_admin.id, node_id=node.id),
        headers=headers,
    )
    device_id = resp.json()["id"]
    client.delete(f"/api/devices/{device_id}", headers=headers)

    # 删除后节点可再绑
    resp = client.post(
        "/api/devices",
        json=_create_payload(name="新机", owner_id=super_admin.id, node_id=node.id),
        headers=headers,
    )
    assert resp.status_code == 201


def test_bindable_nodes_filters(client, db, super_admin, make_node):
    headers = auth_headers(super_admin)
    free = make_node(status="idle", ip="10.0.0.1")
    active = make_node(status="active", ip="10.0.0.2")
    sold = make_node(status="sold", ip="10.0.0.3")

    resp = client.get("/api/devices/bindable-nodes", headers=headers)
    ids = {item["id"] for item in resp.json()["items"]}
    assert ids == {free.id, active.id}
    assert sold.id not in ids

    # 节点可被多台设备共享，已绑定节点仍可选择
    client.post(
        "/api/devices",
        json=_create_payload(owner_id=super_admin.id, node_id=free.id),
        headers=headers,
    )
    resp = client.get("/api/devices/bindable-nodes", headers=headers)
    ids = {item["id"] for item in resp.json()["items"]}
    assert free.id in ids

    # q 搜索
    resp = client.get("/api/devices/bindable-nodes?q=10.0.0.2", headers=headers)
    assert [i["id"] for i in resp.json()["items"]] == [active.id]


# ---------------------------------------------------------------------------
# 审计与日志
# ---------------------------------------------------------------------------

def test_device_logs_recorded_and_parseable(client, db, super_admin):
    headers = auth_headers(super_admin)
    resp = client.post("/api/devices", json=_create_payload(owner_id=super_admin.id), headers=headers)
    device_id = resp.json()["id"]
    client.patch(f"/api/devices/{device_id}", json={"name": "改"}, headers=headers)
    client.delete(f"/api/devices/{device_id}", headers=headers)

    logs = db.query(DeviceLog).filter(DeviceLog.device_id == device_id).order_by(DeviceLog.id).all()
    assert [log.action for log in logs] == ["CREATE", "UPDATE", "DELETE"]
    update_log = logs[1]
    assert update_log.user_id == super_admin.id
    assert update_log.username == "root"
    import json
    changes = json.loads(update_log.changes)
    assert changes["name"]["old"] == "01 测试机"
    assert changes["name"]["new"] == "改"


def test_operation_log_middleware_records_devices(client, db, super_admin):
    headers = auth_headers(super_admin)
    client.post("/api/devices", json=_create_payload(owner_id=super_admin.id), headers=headers)
    resp = client.post("/api/devices", json=_create_payload(name="第二台", owner_id=super_admin.id), headers=headers)
    device_id = resp.json()["id"]

    # PATCH / DELETE 同样落审计（module=终端资产）
    client.patch(f"/api/devices/{device_id}", json={"name": "改"}, headers=headers)
    client.delete(f"/api/devices/{device_id}", headers=headers)

    ops = (
        db.query(OperationLog)
        .filter(OperationLog.module == "终端资产")
        .order_by(OperationLog.id)
        .all()
    )
    assert [op.action for op in ops] == ["CREATE", "CREATE", "UPDATE", "DELETE"]
    assert all(op.result == "success" for op in ops)


def test_device_responses_never_expose_node_credentials(client, db, super_admin, make_node):
    """设备 list/detail 响应不得含节点凭据（username/password/uri 字段白名单防线）。"""
    headers = auth_headers(super_admin)
    node = make_node(status="idle", username="secretuser", password="secretpass")
    resp = client.post(
        "/api/devices",
        json=_create_payload(owner_id=super_admin.id, node_id=node.id),
        headers=headers,
    )
    assert resp.status_code == 201
    device_id = resp.json()["id"]

    for payload in (
        client.get("/api/devices", headers=headers).json(),
        client.get(f"/api/devices/{device_id}", headers=headers).json(),
    ):
        text = json.dumps(payload, ensure_ascii=False)
        assert "secretuser" not in text
        assert "secretpass" not in text
        assert '"uri"' not in text
    # 节点摘要白名单字段
    node_summary = client.get(f"/api/devices/{device_id}", headers=headers).json()["node"]
    assert node_summary == {
        "id": node.id, "ip": node.ip, "port": node.port,
        "protocol": node.protocol, "status": node.status,
    }


def test_cross_owner_node_binding_conflict(client, db, super_admin, normal_user, make_node):
    """非超管可以共享其他设备已绑定的节点。"""
    node = make_node(status="idle")
    # 超管为 alice 建一台绑定该节点的设备
    client.post(
        "/api/devices",
        json=_create_payload(name="alice 的", owner_id=normal_user.id, node_id=node.id),
        headers=auth_headers(super_admin),
    )
    # alice 可以再次绑定同一节点
    resp = client.post(
        "/api/devices",
        json=_create_payload(name="alice 第二台", node_id=node.id),
        headers=auth_headers(normal_user),
    )
    assert resp.status_code == 201


def test_shared_node_relations_preserve_other_devices(client, db, super_admin, make_node):
    headers = auth_headers(super_admin)
    node = make_node(status="active")
    devices = []
    for index in range(3):
        response = client.post("/api/devices", json=_create_payload(
            name=f"shared-{index}", owner_id=super_admin.id,
            node_id=node.id if index == 0 else None,
        ), headers=headers)
        assert response.status_code == 201, response.text
        devices.append(response.json()["id"])
    response = client.patch(f"/api/devices/{devices[1]}", json={"node_id": node.id}, headers=headers)
    assert response.status_code == 200, response.text
    response = client.put(f"/api/devices/{devices[2]}/relations", json={"node_ids": [node.id]}, headers=headers)
    assert response.status_code == 200, response.text
    response = client.put(f"/api/proxy-nodes/{node.id}/relation", json={"device_id": devices[2]}, headers=headers)
    assert response.status_code == 200, response.text
    response = client.get("/api/proxy-nodes", headers=headers)
    linked = next(item for item in response.json()["items"] if item["id"] == node.id)
    assert {item["id"] for item in linked["devices"]} == set(devices)
    response = client.put(f"/api/devices/{devices[2]}/relations", json={"node_ids": []}, headers=headers)
    assert response.status_code == 200, response.text
    for device_id in devices[:2]:
        response = client.get(f"/api/devices/{device_id}", headers=headers)
        assert response.json()["node_id"] == node.id


def test_node_activity_matches_exact_node_and_enforces_scope(client, db, super_admin, normal_user, make_node):
    node = make_node()
    db.add_all([
        OperationLog(username=super_admin.username, module="节点管理", action="UPDATE",
                     summary=f"UPDATE /api/proxy-nodes/{node.id}", result="success"),
        OperationLog(username=super_admin.username, module="节点关联", action="UPDATE",
                     summary=f"UPDATE /api/proxy-nodes/{node.id}/relation", result="failed"),
        OperationLog(username=super_admin.username, module="节点管理", action="UPDATE",
                     summary=f"UPDATE /api/proxy-nodes/{node.id}0", result="success"),
    ])
    db.commit()
    url = f"/api/proxy-nodes/{node.id}/logs"
    response = client.get(url, headers=auth_headers(super_admin))
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 2
    assert {item["summary"] for item in response.json()["items"]} == {"修改节点资料", "调整关联"}
    assert {item["result"] for item in response.json()["items"]} == {"success", "failed"}
    assert client.get(url, headers=auth_headers(normal_user)).status_code == 403
    assert client.get("/api/proxy-nodes/99999/logs", headers=auth_headers(super_admin)).status_code == 404


def test_device_activity_uses_readable_names_and_omits_empty_changes(client, db, super_admin, make_node):
    from app.services.device_service import readable_device_log

    node = make_node(ip="186.233.6.246", port=44000)
    headers = auth_headers(super_admin)
    response = client.post("/api/devices", json=_create_payload(
        name="天05", device_type="phone", owner_id=super_admin.id, node_id=node.id,
    ), headers=headers)
    assert response.status_code == 201, response.text
    device_id = response.json()["id"]
    response = client.get(f"/api/devices/{device_id}/logs", headers=headers)
    assert response.status_code == 200, response.text
    log = response.json()["items"][0]
    assert log["summary"] == "新增手机 天05"
    assert "关联节点：186.233.6.246:44000" in log["details"]
    assert all("ID" not in detail and "未设置 → 未设置" not in detail for detail in log["details"])
    account = OpAccount(platform="tiktok", account="visible-account")
    db.add(account)
    db.commit()
    changes = {"relations": {"old": {"account_ids": [], "node_ids": [node.id]},
                              "new": {"account_ids": [account.id], "node_ids": []}}}
    summary = readable_device_log(db, DeviceLog(action="UPDATE", changes=json.dumps(changes)))
    assert summary["summary"] == "调整终端关联"
    assert set(summary["details"]) == {"解除节点：186.233.6.246:44000", "关联账号：visible-account"}


def test_owner_reassignment(client, db, super_admin, other_user):
    headers = auth_headers(super_admin)
    resp = client.post(
        "/api/devices",
        json=_create_payload(owner_id=super_admin.id),
        headers=headers,
    )
    device_id = resp.json()["id"]

    # 超管改 owner → 200
    resp = client.patch(
        f"/api/devices/{device_id}",
        json={"owner_id": other_user.id},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["owner_id"] == other_user.id

    # owner 不存在 → 404
    resp = client.patch(
        f"/api/devices/{device_id}",
        json={"owner_id": 99999},
        headers=headers,
    )
    assert resp.status_code == 404


def test_deleted_device_logs_404_for_former_owner(client, db, super_admin, normal_user):
    """设备软删除后：原 owner（非超管）查 logs → 404，防止已删除信息泄露。"""
    resp = client.post(
        "/api/devices",
        json=_create_payload(owner_id=normal_user.id),
        headers=auth_headers(super_admin),
    )
    device_id = resp.json()["id"]

    # 删除前 owner 可查 logs
    assert client.get(
        f"/api/devices/{device_id}/logs", headers=auth_headers(normal_user)
    ).status_code == 200

    client.delete(f"/api/devices/{device_id}", headers=auth_headers(super_admin))

    # 删除后 owner 查 logs → 404
    assert client.get(
        f"/api/devices/{device_id}/logs", headers=auth_headers(normal_user)
    ).status_code == 404


def test_node_relation_rejects_node_edit_fields(client, super_admin, make_node):
    node = make_node()
    resp = client.put(f"/api/proxy-nodes/{node.id}/relation", json={"ip": "9.9.9.9"}, headers=auth_headers(super_admin))
    assert resp.status_code == 422


def test_device_relations_multi_node_and_round_trip(client, db, super_admin, make_node):
    headers = auth_headers(super_admin)
    first = make_node(status="idle", ip="10.1.0.1")
    second = make_node(status="active", ip="10.1.0.2", port=1081)
    device = client.post("/api/devices", json=_create_payload(owner_id=super_admin.id, device_type="phone"), headers=headers).json()
    account_payload = {"platform": "tiktok", "account": "relation-user"}
    account = client.post("/api/op-accounts", json=account_payload, headers=headers)
    assert account.status_code == 201, account.text
    saved = client.put(f"/api/devices/{device['id']}/relations", json={"account_id": account.json()["id"], "node_ids": [first.id, second.id]}, headers=headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["node_ids"] == [first.id, second.id]
    listed = client.get("/api/devices", headers=headers).json()["items"]
    assert next(item for item in listed if item["id"] == device["id"])["node_ids"] == [first.id, second.id]
    logs = client.get(f"/api/devices/{device['id']}/logs", headers=headers).json()["items"]
    assert any("relations" in (item.get("changes") or {}) for item in logs)


def test_node_relation_account_and_device_round_trip(client, db, super_admin, make_node):
    headers = auth_headers(super_admin)
    node = make_node(status="idle")
    device = client.post("/api/devices", json=_create_payload(owner_id=super_admin.id, device_type="phone"), headers=headers).json()
    account = client.post("/api/op-accounts", json={"platform": "tiktok", "account": "node-user"}, headers=headers).json()
    bound = client.put(f"/api/proxy-nodes/{node.id}/relation", json={"device_id": device["id"], "account_id": account["id"]}, headers=headers)
    assert bound.status_code == 200, bound.text
    assert db.query(Device).filter(Device.id == device["id"]).one().node_id == node.id
    assert db.query(OpAccount).filter(OpAccount.id == account["id"]).one().node_id == node.id
    cleared = client.put(f"/api/proxy-nodes/{node.id}/relation", json={"device_id": None, "account_id": None}, headers=headers)
    assert cleared.status_code == 200, cleared.text


def test_proxy_node_stats_super_admin_scope(client, super_admin, make_node):
    """超管统计入口保持全量可用，范围过滤不会破坏基础响应。"""
    headers = auth_headers(super_admin)
    make_node(status="idle")
    make_node(status="active")
    response = client.get("/api/proxy-nodes/stats", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 2


def test_account_inherits_device_node_without_changing_device(client, db, super_admin, make_node):
    headers = auth_headers(super_admin)
    first, second = make_node(), make_node(ip="10.0.0.2")
    device = client.post("/api/devices", json=_create_payload(
        owner_id=super_admin.id, device_type="phone", node_id=first.id,
    ), headers=headers).json()
    account = OpAccount(platform="tiktok", account="inherited-node", registrant=super_admin.username)
    db.add(account)
    db.commit()
    url = f"/api/op-accounts/{account.id}"
    response = client.put(url, json={"device_id": device["id"]}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["node_id"] == first.id
    response = client.get("/api/proxy-nodes", headers=headers)
    assert response.status_code == 200, response.text
    linked = next(n for n in response.json()["items"] if n["id"] == first.id)
    assert linked["accounts"][0]["username"] == "inherited-node"
    assert client.put(url, json={"node_id": second.id}, headers=headers).status_code == 409
    assert client.put(f"/api/proxy-nodes/{second.id}/relation",
                      json={"account_id": account.id}, headers=headers).status_code == 409
    response = client.patch(f"/api/devices/{device['id']}", json={"node_id": second.id}, headers=headers)
    assert response.status_code == 200, response.text
    db.refresh(account)
    assert account.node_id == second.id
    response = client.put(url, json={"device_id": None}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["node_id"] is None
    response = client.get(f"/api/devices/{device['id']}", headers=headers)
    assert response.json()["node_ids"] == [second.id]
    response = client.put(f"/api/devices/{device['id']}/relations",
                          json={"account_id": account.id, "node_ids": []}, headers=headers)
    assert response.status_code == 200, response.text
    db.refresh(account)
    assert account.device_id == device["id"] and account.node_id is None
    response = client.put(url, json={"device_id": device["id"]}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["node_id"] is None


def test_proxy_node_list_returns_relation_fields(client, super_admin, make_node):
    node = make_node()
    response = client.get("/api/proxy-nodes?skip=0&limit=50", headers=auth_headers(super_admin))
    assert response.status_code == 200, response.text
    item = next(value for value in response.json()["items"] if value["id"] == node.id)
    assert item["accounts"] == []

def test_concurrent_node_binding_single_winner(client, super_admin, make_node, monkeypatch):
    """并发绑定同一节点允许多台设备共享。"""
    import threading
    import tempfile
    import pathlib

    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker

    from app.core.database import Base, get_db
    import app.middleware.operation_log as op_log_module

    tmp_db = pathlib.Path(tempfile.mkdtemp()) / "race.db"
    race_engine = create_engine(
        f"sqlite:///{tmp_db}",
        connect_args={"check_same_thread": False, "timeout": 15},
    )

    @event.listens_for(race_engine, "connect")
    def _fk_on(dbapi_conn, record):  # noqa: ANN001
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=race_engine)
    race_factory = sessionmaker(autocommit=False, autoflush=False, bind=race_engine)

    def _get_db_override():
        session = race_factory()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(op_log_module, "SessionLocal", race_factory)
    app_under_test = client.app
    app_under_test.dependency_overrides[get_db] = _get_db_override

    # 种子：超管 + 空闲节点
    from app.core.security import hash_password
    from app.models.team import User as UserModel
    from app.models.proxy_node import ProxyNode as PN
    seed = race_factory()
    admin = UserModel(username="raceadmin", password_hash=hash_password("x"), is_super_admin=True, is_active=True)
    seed.add(admin)
    seed.flush()
    node = PN(ip="6.6.6.6", port=1080, protocol="socks5", status="idle")
    seed.add(node)
    seed.commit()
    seed.refresh(node)
    # 会话关闭前取好 token 与 id（防 DetachedInstanceError）
    headers = auth_headers(admin)
    admin_id = admin.id
    node_id = node.id
    seed.close()

    results = []
    barrier = threading.Barrier(2)

    def _bind():
        barrier.wait(timeout=10)
        r = client.post(
            "/api/devices",
            json=_create_payload(name="并发机", owner_id=admin_id, node_id=node_id),
            headers=headers,
        )
        results.append(r.status_code)

    threads = [threading.Thread(target=_bind) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(results) == [201, 201], results

    check = race_factory()
    from app.models.device import Device as DeviceModel
    bound = check.query(DeviceModel).filter(
        DeviceModel.node_id == node_id, DeviceModel.is_deleted == False
    ).count()
    assert bound == 2
    check.close()
