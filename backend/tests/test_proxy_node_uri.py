"""节点代理 URI（二维码）测试：纯函数构建规则 + 超管端点 + 审计保密。"""
import pytest
from types import SimpleNamespace

from app.models.team import OperationLog
from app.services.proxy_node_service import build_node_uri

from .conftest import auth_headers


def _node(**kw):
    defaults = dict(
        ip="1.2.3.4", port=1080, username=None, password=None,
        protocol="socks5", relay_ip=None, relay_port=None, relay_protocol=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# build_node_uri 纯函数
# ---------------------------------------------------------------------------

def test_uri_direct_with_credentials():
    node = _node(username="user", password="p@ss")
    assert build_node_uri(node) == "socks5://user:p%40ss@1.2.3.4:1080"


@pytest.mark.parametrize("username,password", [
    ("a/b", "c/d"),
    ("a:b", "c:d"),
    ("a#b", "c#d"),
    ("a?b", "c?d"),
    ("a%b", "c%d"),
    ("a b", "c d"),
    ("中文用户", "中文密码"),
])
def test_uri_escapes_reserved_chars_in_credentials(username, password):
    node = _node(username=username, password=password)
    uri = build_node_uri(node)
    # 拆出 auth 段（schema 与第一个 @ 之间），再逐段解码验证与原文一致
    auth_part = uri.split("://", 1)[1].rsplit("@", 1)[0]
    from urllib.parse import unquote
    assert unquote(auth_part) == f"{username}:{password}"


def test_uri_omits_auth_when_credentials_incomplete():
    # 仅用户名或仅密码或全空：都不输出 user:pass@ 段
    assert build_node_uri(_node(username="onlyuser")) == "socks5://1.2.3.4:1080"
    assert build_node_uri(_node(password="onlypass")) == "socks5://1.2.3.4:1080"
    assert build_node_uri(_node()) == "socks5://1.2.3.4:1080"


def test_uri_relay_priority_and_partial_fallback():
    # 中转齐全 → 用中转（含中转凭据）
    node = _node(
        username="u", password="p",
        relay_ip="5.6.7.8", relay_port=2080, relay_protocol="http",
    )
    assert build_node_uri(node) == "http://u:p@5.6.7.8:2080"
    # relay 部分字段缺失 → 回退直连
    node.relay_protocol = None
    assert build_node_uri(node) == "socks5://u:p@1.2.3.4:1080"


def test_uri_ipv6_brackets_and_protocol_normalization():
    assert build_node_uri(_node(ip="::1", protocol="SOCKS5")) == "socks5://[::1]:1080"
    # IPv6 zone 标识保留在括号内
    assert build_node_uri(_node(ip="fe80::1%eth0")) == "socks5://[fe80::1%eth0]:1080"
    # 已带括号的主机不重复加括号
    assert build_node_uri(_node(ip="[::1]")) == "socks5://[::1]:1080"


def test_uri_invalid_protocol_raises():
    with pytest.raises(ValueError):
        build_node_uri(_node(protocol="ftp"))
    # 中转协议非法：拒绝而非静默回退
    with pytest.raises(ValueError):
        build_node_uri(_node(relay_ip="5.6.7.8", relay_port=2080, relay_protocol="ftp"))


def test_uri_invalid_host_raises():
    for bad in ("1.2.3.4/evil", "a b", "1.2.3.4@x", "a#b"):
        with pytest.raises(ValueError):
            build_node_uri(_node(ip=bad))


def test_uri_missing_host_or_port_raises():
    with pytest.raises(ValueError):
        build_node_uri(_node(ip=None))
    with pytest.raises(ValueError):
        build_node_uri(_node(port=None))


# ---------------------------------------------------------------------------
# URI 端点
# ---------------------------------------------------------------------------

def test_uri_endpoint_super_admin_only(client, db, super_admin, normal_user, make_node):
    node = make_node(status="idle", ip="9.9.9.9", port=8080, username="u", password="p")

    # 非超管 403
    resp = client.get(f"/api/proxy-nodes/{node.id}/uri", headers=auth_headers(normal_user))
    assert resp.status_code == 403

    # 超管 200
    resp = client.get(f"/api/proxy-nodes/{node.id}/uri", headers=auth_headers(super_admin))
    assert resp.status_code == 200
    assert resp.json()["uri"] == "socks5://u:p@9.9.9.9:8080"


def test_uri_endpoint_status_policy(client, db, super_admin, make_node):
    headers = auth_headers(super_admin)
    for status in ("sold", "disabled"):
        node = make_node(status=status)
        resp = client.get(f"/api/proxy-nodes/{node.id}/uri", headers=headers)
        assert resp.status_code == 400, f"{status}: {resp.text}"


def test_uri_endpoint_not_found(client, db, super_admin):
    resp = client.get("/api/proxy-nodes/99999/uri", headers=auth_headers(super_admin))
    assert resp.status_code == 404


def test_uri_endpoint_audited_without_secret_leak(client, db, super_admin, make_node):
    """审计落库且任何日志字段都不含 URI 与凭据明文。"""
    node = make_node(status="idle", username="secretuser", password="secretpass")
    resp = client.get(f"/api/proxy-nodes/{node.id}/uri", headers=auth_headers(super_admin))
    uri = resp.json()["uri"]
    assert "secretuser" in uri and "secretpass" in uri  # 响应本身含凭据（供扫码）

    ops = (
        db.query(OperationLog)
        .filter(OperationLog.module == "节点管理", OperationLog.action == "VIEW_SECRET")
        .all()
    )
    assert len(ops) == 1
    assert ops[0].result == "success"
    # 审计保密：日志任一字段不得泄露 URI 或凭据
    for field in ("username", "ip_address", "summary", "error", "module", "action"):
        value = str(getattr(ops[0], field, "") or "")
        assert "secretuser" not in value
        assert "secretpass" not in value
        assert uri not in value
