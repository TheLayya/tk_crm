import pytest

from app.models.op_account import OpAccount, OpAuditLog
from tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def clean_accounts(db, clean_tables):
    yield
    db.rollback()
    db.query(OpAuditLog).delete()
    db.query(OpAccount).filter(OpAccount.account.like("sale-test-%")).delete()
    db.commit()


@pytest.mark.parametrize("missing", [
    {"sale_customer": " "}, {"sale_price": None}, {"sale_price": -1},
    {"sellers": []}, {"sellers": [" "]}, {"sale_date": None},
])
def test_operation_account_sale_requires_all_fields(client, db, super_admin, missing):
    headers = auth_headers(super_admin)
    sale = {"status": "已售", "sale_customer": "客户", "sale_price": 0,
            "sale_date": "2026-10-01", "sellers": ["root"]}
    created = client.post("/api/op-accounts", headers=headers, json={
        "platform": "youtube", "account": "sale-test-created", **sale, **missing,
    })
    assert created.status_code == 422, created.text
    account = OpAccount(platform="youtube", account="sale-test-update", status="正常")
    db.add(account)
    db.commit()
    url = f"/api/op-accounts/{account.id}"
    assert client.put(url, headers=headers, json={**sale, **missing}).status_code == 422
    batch = client.post("/api/op-accounts/batch-status", headers=headers,
                        json={"ids": [account.id], **sale, **missing})
    assert batch.status_code == 422, batch.text
    db.refresh(account)
    assert account.status == "正常"
    valid = client.put(url, headers=headers, json=sale)
    assert valid.status_code == 200, valid.text
    assert client.put(url, headers=headers, json={"sale_price": None}).status_code == 422
    assert client.put(url, headers=headers, json={"remark": "交付完成"}).status_code == 200
    reverted = client.put(url, headers=headers, json={"status": "正常"})
    assert reverted.status_code == 200, reverted.text
    assert reverted.json()["sale_customer"] == "客户"


@pytest.mark.parametrize("missing", [
    {"sale_customer": " "}, {"sale_price": None}, {"sale_price": -1},
    {"sellers": []}, {"sellers": [" "]},
])
def test_node_sale_requires_all_fields(client, db, super_admin, make_node, missing):
    headers = auth_headers(super_admin)
    sale = {"status": "sold", "sale_customer": "客户", "sale_price": 0, "sellers": ["root"]}
    response = client.post("/api/proxy-nodes", headers=headers,
                           json={"ip": "10.100.0.1", "port": 1080, **sale, **missing})
    assert response.status_code == 422, response.text
    node = make_node()
    url = f"/api/proxy-nodes/{node.id}"
    assert client.patch(url, headers=headers, json={**sale, **missing}).status_code == 422
    batch = client.patch("/api/proxy-nodes/batch/status", headers=headers,
                         json={"node_ids": [node.id], **sale, **missing})
    assert batch.status_code == 422, batch.text
    db.refresh(node)
    assert node.status == "idle"
    valid = client.patch("/api/proxy-nodes/batch/status", headers=headers,
                         json={"node_ids": [node.id], **sale})
    assert valid.status_code == 200, valid.text
    assert client.patch(url, headers=headers, json={"sellers": []}).status_code == 422
    assert client.patch(url, headers=headers, json={"remark": "交付完成"}).status_code == 200
    reverted = client.patch(url, headers=headers, json={"status": "idle"})
    assert reverted.status_code == 200, reverted.text
    assert reverted.json()["sale_customer"] == "客户"


def test_operation_account_batch_sale_keeps_zero_price(client, db, super_admin):
    account = OpAccount(platform="youtube", account="sale-test-batch", status="正常")
    db.add(account)
    db.commit()
    response = client.post("/api/op-accounts/batch-status", headers=auth_headers(super_admin), json={
        "ids": [account.id], "status": "已售", "sale_customer": "客户", "sale_price": 0,
        "sale_date": "2026-10-01", "sellers": ["root"],
    })
    assert response.status_code == 200, response.text
    db.refresh(account)
    assert account.status == "已售"
    assert account.sale_price == 0
