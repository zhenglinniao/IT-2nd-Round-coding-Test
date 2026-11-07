import asyncio

import httpx
import pytest

from backend.app.config import Settings
from backend.app.models import Shipment
from backend.app.tracking import TrackingService, normalize_auspost

SHIPMENT = Shipment(id="parcel", carrier="startrack", tracking_number="TEST123")
SETTINGS = Settings(auspost_key="fixture-key", auspost_secret="fixture-secret", startrack_account="00000000")


@pytest.mark.parametrize("shape", ["consignment", "article", "nested"])
def test_normalize_supported_shapes_with_ordered_events(shape):
    node = {"status": "Delivered", "events": [
        {"description": "Picked up", "date": "2025-12-01T13:00:00+11:00"},
        {"description": "Delivered", "location": "MEL", "date": "2025-12-02T09:00:00+11:00"},
    ]}
    result = {"tracking_id": "TEST123"}
    if shape == "consignment":
        result["consignment"] = node
    elif shape == "article":
        result["trackable_items"] = [node]
    else:
        result["trackable_items"] = [{"items": [node]}]
    normalized = normalize_auspost({"tracking_results": [result]}, "TEST123")
    assert normalized["query_state"] == "available"
    assert normalized["status"] == "Delivered"
    assert normalized["last_update"] == "2025-12-02T09:00:00+11:00"
    assert normalized["events"][0]["description"] == "Delivered"


@pytest.mark.parametrize("payload,state", [
    (None, "invalid_response"),
    ({"tracking_results": []}, "not_found"),
    ({"tracking_results": [{"tracking_id": "OTHER", "status": "Delivered"}]}, "not_found"),
    ({"tracking_results": [{"tracking_id": "TEST123"}]}, "unavailable"),
    ({"tracking_results": [{"tracking_id": "TEST123", "errors": [{"code": "ESB-10001"}]}]}, "not_found"),
    ({"tracking_results": [{"tracking_id": "TEST123", "errors": [{"code": "ESB-20010"}]}]}, "upstream_error"),
    ({"tracking_results": [{"tracking_id": "TEST123", "events": "bad"}]}, "invalid_response"),
])
def test_empty_invalid_or_unmatched_payload_never_fabricates_result(payload, state):
    assert normalize_auspost(payload, "TEST123")["query_state"] == state


def test_missing_dates_and_status_remain_missing():
    result = normalize_auspost({"tracking_results": [{"tracking_id": "TEST123", "events": [{"description": "Event received"}]}]}, "TEST123")
    assert result["last_update"] is None and result["status"] is None


def test_mixed_article_statuses_are_not_misrepresented_as_all_delivered():
    result = normalize_auspost({"tracking_results": [{"tracking_id": "TEST123", "trackable_items": [{"status": "Delivered"}, {"status": "In Transit"}]}]}, "TEST123")
    assert result["status"] == "Delivered / In Transit"


@pytest.mark.anyio
@pytest.mark.parametrize("code,state", [(401, "authentication_failed"), (403, "authentication_failed"), (429, "rate_limited"), (500, "upstream_error"), (200, "invalid_response"), (302, "invalid_response")])
async def test_http_errors_are_safe_and_cached(code, state):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(code, text="not JSON, potentially sensitive upstream body")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = TrackingService(SETTINGS, client)
        first, second = await asyncio.gather(service.track(SHIPMENT), service.track(SHIPMENT))
    assert first["query_state"] == state and second["cached"]
    assert len(requests) == 1
    assert requests[0].url.params["tracking_ids"] == "TEST123"
    assert requests[0].headers["Account-Number"] == "00000000"
    assert "fixture-secret" not in str(first) and "sensitive" not in str(first)


@pytest.mark.anyio
@pytest.mark.parametrize("exception,state", [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "network_error")])
async def test_transport_failures(exception, state):
    def handler(request):
        raise exception("private connection details", request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await TrackingService(SETTINGS, client).track(SHIPMENT)
    assert result["query_state"] == state
    assert "private" not in str(result)


@pytest.mark.anyio
async def test_no_configuration_and_tnt_do_not_send_requests():
    def forbidden(request):
        pytest.fail("No request expected")
    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as client:
        service = TrackingService(Settings(), client)
        assert (await service.track(SHIPMENT))["query_state"] == "not_configured"
        assert (await service.track(SHIPMENT.model_copy(update={"carrier": "tnt"})))["query_state"] == "not_configured"


@pytest.mark.anyio
async def test_testbed_rate_limit_does_not_send_eleventh_request():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"tracking_results": []})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = TrackingService(SETTINGS, client)
        for i in range(11):
            result = await service.track(SHIPMENT.model_copy(update={"tracking_number": f"TEST{i}"}))
    assert result["query_state"] == "rate_limited"
    assert len(requests) == 10


def test_config_rejects_credential_exfiltration_endpoint():
    with pytest.raises(ValueError):
        Settings(auspost_base_url="https://untrusted.example/test/shipping/v1")
