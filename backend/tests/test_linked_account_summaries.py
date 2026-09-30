"""Linked account cards use summaries from the isolated, in-memory API database."""
import pytest

from app.models.device import Device
from app.models.op_account import OpAccount, OpAuditLog
from tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def clean_accounts(db, clean_tables):
    yield
    db.rollback()
    for model in (OpAuditLog, OpAccount):
        db.query(model).delete()
    db.commit()


@pytest.mark.parametrize("endpoint,name_field", [
    ("/api/devices", "account"),
    ("/api/proxy-nodes", "username"),
])
def test_linked_account_summaries_preserve_all_accounts_and_metrics(
    client, db, super_admin, make_node, endpoint, name_field
):
    node = make_node()
    empty_node = make_node(ip="5.6.7.8")
    device = Device(name="linked phone", device_type="phone", owner_id=super_admin.id,
                    node_id=node.id)
    empty_device = Device(name="empty phone", device_type="phone", owner_id=super_admin.id,
                          node_id=empty_node.id)
    db.add_all([device, empty_device])
    db.flush()
    accounts = [
        OpAccount(
            platform="tiktok", account=f"linked-{index}", device_id=device.id,
            node_id=node.id, nickname=f"Nickname {index}" if value is not None else None,
            avatar_url=f"https://example.test/avatar-{index}.png" if value is not None else None,
            follower_count=value, following_count=value, like_count=value, video_count=value,
            password="account-secret", email_password="email-secret", totp_secret="totp-secret",
        )
        for index, value in enumerate((419, 0, None))
    ]
    db.add_all(accounts)
    db.add(OpAccount(platform="tiktok", account="unlinked"))
    db.commit()

    response = client.get(endpoint, headers=auth_headers(super_admin))
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 2
    items = {item["id"]: item for item in response.json()["items"]}
    linked = items[device.id if name_field == "account" else node.id]
    empty = items[empty_device.id if name_field == "account" else empty_node.id]
    assert empty["accounts"] == []
    summaries = {account["id"]: account for account in linked["accounts"]}
    assert set(summaries) == {account.id for account in accounts}
    for account in accounts:
        expected = {
            "id": account.id,
            name_field: account.account,
            "nickname": account.nickname,
            "avatar_url": account.avatar_url,
            "follower_count": account.follower_count,
            "following_count": account.following_count,
            "like_count": account.like_count,
            "video_count": account.video_count,
        }
        if name_field == "account":
            expected["platform"] = account.platform
        else:
            expected["device_id"] = device.id
        # An exact whitelist also prevents passwords or other private account fields leaking.
        assert summaries[account.id] == expected

    if name_field == "account":
        assert linked["account_id"] == accounts[0].id
        assert linked["account_name"] == accounts[0].account
    else:
        assert linked["account_count"] == 3
        assert set(linked["account_ids"]) == set(summaries)
    db.expire_all()
    assert [(account.device_id, account.node_id) for account in accounts] == [
        (device.id, node.id)
    ] * 3
