import asyncio
from urllib.parse import parse_qs

import httpx
import pytest

from backend.app.config import Settings
from backend.app.models import Shipment
from backend.app.tnt import ORIGIN, normalize_history
from backend.app.tracking import TrackingService

NUMBER = "305506914"
SHIPMENT = Shipment(id="tnt", carrier="tnt", tracking_number=NUMBER)
FORM = '<input type="hidden" name="__VIEWSTATE" value="fixture"><input type="hidden" name="__EVENTVALIDATION" value="fixture">'
RESULT = FORM + '<a id="bodycontent_A1">View Details</a>'
# Minimal fixture reproduces the observed official history DOM, with no cookies,
# ASP.NET state, credentials, recipient name or other personal information.
HISTORY = '''<div id="bodycontent_divcollection"><p>Consignment: 305506914</p>
<table><tr><th>Status</th><th>Date &amp; Time</th><th>Depot</th></tr>
<tr><td>We've collected your shipment</td><td>03/12/2025 15:27</td><td>Sydney - Enfield</td></tr>
<tr><td>We've delivered your shipment</td><td>04/12/2025 13:00</td><td>Melbourne - Airport</td></tr>
</table></div>'''


def test_history_matches_number_orders_events_and_preserves_unzoned_time():
    result = normalize_history(HISTORY, NUMBER)
    assert result["status"] == "We've delivered your shipment"
    assert result["last_update"] is None
    assert result["last_update_text"] == "04/12/2025 13:00"
    assert result["events"][0]["date"] is None
    assert result["events"][0]["location"] == "Melbourne - Airport"
    assert len(result["events"]) == 2


@pytest.mark.parametrize("html", ["<html>error</html>", HISTORY.replace(NUMBER, "999999999"), HISTORY.replace("Date &amp; Time", "Changed"), HISTORY.replace("04/12/2025 13:00", "unknown")])
def test_changed_or_mismatched_history_never_fabricates_delivery(html):
    with pytest.raises(ValueError):
        normalize_history(html, NUMBER)


@pytest.mark.anyio
async def test_public_flow_is_read_only_cached_and_never_sends_credentials():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.host == "www.tntexpress.com.au"
        assert "authorization" not in request.headers
        if request.method == "POST":
            fields = parse_qs(request.content.decode())
            target = fields["__EVENTTARGET"][0]
            if target.endswith("btnSubmit"):
                assert fields["TextArea"] == [NUMBER] and fields["method"] == ["CON"]
                path = "/interaction/trackntraceResult.aspx?con=fixture"
            else:
                assert target == "ctl00$bodycontent$A1"
                path = "/interaction/ConsignmentHistory.aspx?con=fixture"
            return httpx.Response(302, headers={"location": path})
        return httpx.Response(200, text=HISTORY if "ConsignmentHistory" in request.url.path else RESULT if "Result" in request.url.path else FORM)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = TrackingService(Settings(tnt_enabled=True), client)
        first, second = await asyncio.gather(service.track(SHIPMENT), service.track(SHIPMENT))
    assert first["query_state"] == "available" and second["cached"]
    assert first["environment"] == "tnt_public"
    assert len(calls) == 5


@pytest.mark.anyio
@pytest.mark.parametrize("location", ["https://untrusted.example/interaction/trackntraceResult.aspx", ORIGIN + "/webservices/conservice/ConsignmentService.svc", "http://www.tntexpress.com.au/interaction/trackntraceResult.aspx"])
async def test_redirects_cannot_leave_approved_read_only_routes(location):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, text=FORM) if request.method == "GET" else httpx.Response(302, headers={"location": location})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await TrackingService(Settings(tnt_enabled=True), client).track(SHIPMENT)
    assert result["query_state"] == "invalid_response" and len(calls) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("code,state", [(403, "authentication_failed"), (429, "rate_limited"), (500, "upstream_error"), (200, "invalid_response")])
async def test_upstream_errors_are_safe(code, state):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(code, text="private upstream data"))) as client:
        result = await TrackingService(Settings(tnt_enabled=True), client).track(SHIPMENT)
    assert result["query_state"] == state
    assert "private" not in str(result)


@pytest.mark.anyio
@pytest.mark.parametrize("exception,state", [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "network_error")])
async def test_network_failure(exception, state):
    def handler(request):
        raise exception("private detail", request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await TrackingService(Settings(tnt_enabled=True), client).track(SHIPMENT)
    assert result["query_state"] == state


@pytest.mark.anyio
async def test_unsupported_number_sends_no_request():
    def forbidden(request):
        pytest.fail("Unsupported number must not be sent")
    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as client:
        result = await TrackingService(Settings(tnt_enabled=True), client).track(SHIPMENT.model_copy(update={"tracking_number": "ABC"}))
    assert result["query_state"] == "unsupported_number"
