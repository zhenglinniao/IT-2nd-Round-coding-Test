import json

import httpx
from fastapi.testclient import TestClient

from backend.app.config import ROOT, Settings
from backend.app.main import create_app


def test_list_detail_unknown_and_tracking_degradation():
    with TestClient(create_app(Settings(data_dir=ROOT / "data"))) as client:
        assert client.get("/api/health").json()["data_ready"]
        orders = client.get("/api/orders").json()["orders"]
        assert len(orders) == 2
        detail = client.get(f"/api/orders/{orders[1]['id']}").json()
        assert len(detail["shipments"]) == 2
        assert detail["totals"]["total"] == "1655.00"
        assert client.get("/api/orders/UNKNOWN").status_code == 404
        tracking = client.get(f"/api/orders/{orders[1]['id']}/tracking").json()["shipments"]
        assert [r["query_state"] for r in tracking] == ["not_configured", "not_configured"]
        assert tracking[0]["message"] == "服务端尚未配置完整的快递查询凭据。"
        assert client.get(f"/api/orders/{orders[1]['id']}").status_code == 200


def test_unreadable_data_does_not_kill_health(data_dir):
    (data_dir / "orders.json").write_text("broken")
    with TestClient(create_app(Settings(data_dir=data_dir))) as client:
        assert client.get("/api/health").json() == {"status": "ok", "data_ready": False}
        response = client.get("/api/orders")
        assert response.status_code == 503
        assert "orders.json" in response.json()["detail"]


def test_invalid_order_is_listed_and_detail_returns_422(data_dir, order_raw):
    order_raw["items"][0]["quantity"] = 0
    (data_dir / "orders.json").write_text(json.dumps([order_raw]))
    with TestClient(create_app(Settings(data_dir=data_dir))) as client:
        assert not client.get("/api/orders").json()["orders"][0]["complete"]
        assert client.get(f"/api/orders/{order_raw['id']}").status_code == 422
        problems = client.get(f"/api/orders/{order_raw['id']}").json()["detail"]["problems"]
        assert any("必须大于" in problem for problem in problems)


def test_empty_and_missing_catalog(data_dir, order_raw):
    (data_dir / "products.json").write_text("[]")
    with TestClient(create_app(Settings(data_dir=data_dir))) as client:
        detail = client.get(f"/api/orders/{order_raw['id']}").json()
        assert detail["totals"] is None and not detail["complete"]
    (data_dir / "orders.json").write_text("[]")
    with TestClient(create_app(Settings(data_dir=data_dir))) as client:
        assert client.get("/api/orders").json()["orders"] == []


def test_partial_tracking_failure_keeps_second_package_result():
    def handler(request):
        return httpx.Response(403, text="private upstream error")
    settings = Settings(auspost_key="fixture", auspost_secret="fixture", startrack_account="00000000")
    with TestClient(create_app(settings, transport=httpx.MockTransport(handler))) as client:
        response = client.get("/api/orders/PO-20251203-00046/tracking")
        assert response.status_code == 200
        assert [s["query_state"] for s in response.json()["shipments"]] == ["authentication_failed", "not_configured"]
        assert "private" not in response.text
