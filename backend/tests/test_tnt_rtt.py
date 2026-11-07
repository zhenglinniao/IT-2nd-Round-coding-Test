from datetime import date, datetime, timezone
from urllib.parse import parse_qs, unquote
from xml.etree import ElementTree as ET

import httpx
import pytest

from backend.app.config import Settings
from backend.app.tnt_rtt import NAMESPACE, URL, normalize_rtt, probe_rtt

SETTINGS = Settings(tnt_uat_username="fixture-user", tnt_uat_password="fixture-password", tnt_uat_account="12345678")
DAY = date(2026, 11, 9)
NOW = datetime(2026, 11, 7, 3, 0, tzinfo=timezone.utc)
QUOTES = '''<response xmlns="http://www.tntexpress.com.au"><ratedTransitTimeResponse><ratedProducts>
<ratedProduct><product><code>EX12</code></product><quote currency="AUD"><price>32.57</price></quote></ratedProduct>
<ratedProduct><product><code>75</code></product><quote currency="AUD"><price>15.42</price></quote></ratedProduct>
</ratedProducts></ratedTransitTimeResponse></response>'''
AUTH_ERROR = '<response><error><code>004</code><description>private upstream</description></error></response>'
RULE_ERROR = '''<response xmlns="http://www.tntexpress.com.au"><ratedTransitTimeResponse><brokenRules>
<brokenRule><code>590</code><description>private upstream</description></brokenRule>
</brokenRules></ratedTransitTimeResponse></response>'''


def test_normalizes_observed_quotes_authentication_error_and_business_rule():
    quotes = normalize_rtt(QUOTES)
    assert quotes["query_state"] == "available"
    assert quotes["quotes"] == [{"service_code": "EX12", "currency": "AUD", "price": "32.57"}, {"service_code": "75", "currency": "AUD", "price": "15.42"}]
    assert normalize_rtt(AUTH_ERROR)["query_state"] == "authentication_failed"
    assert normalize_rtt(AUTH_ERROR)["error_codes"] == ["004"]
    assert normalize_rtt(RULE_ERROR)["query_state"] == "invalid_request"
    assert normalize_rtt(RULE_ERROR)["error_codes"] == ["590"]
    assert "private upstream" not in str(normalize_rtt(RULE_ERROR))


@pytest.mark.parametrize("payload", [QUOTES.replace("32.57", "NaN"), QUOTES.replace("32.57", "-1"), QUOTES.replace("32.57", "1.001"), QUOTES.replace('currency="AUD"', 'currency="USD"'), '<response/>', '<html/>', '<!DOCTYPE response [<!ENTITY x "test">]><response/>'])
def test_invalid_or_unsafe_quote_is_never_reported_available(payload):
    with pytest.raises(ValueError):
        normalize_rtt(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("case", ["valid", "invalid_password", "invalid_route"])
async def test_correct_uat_endpoint_form_encoding_and_sample_no_booking(case):
    calls = []
    def handler(request):
        calls.append(request)
        assert request.method == "POST" and str(request.url) == URL and not request.url.query
        fields = parse_qs(request.content.decode())
        assert set(fields) == {"Username", "Password", "Version", "XMLRequest"}
        assert fields["Version"] == ["2"]
        assert fields["Username"] == ["fixture-user"]
        assert fields["Password"] == ["__intentional_invalid_control__" if case == "invalid_password" else "fixture-password"]
        assert fields["XMLRequest"][0].startswith("%3C")
        root = ET.fromstring(unquote(fields["XMLRequest"][0]))
        ns = {"r": NAMESPACE}
        assert root.findtext("r:ratedTransitTimeEnquiry/r:cutOffTimeEnquiry/r:collectionAddress/r:suburb", namespaces=ns) == ("RYDE" if case == "invalid_route" else "GLADESVILLE")
        assert root.findtext("r:ratedTransitTimeEnquiry/r:termsOfPayment/r:senderAccount", namespaces=ns) == "12345678"
        assert root.findtext("r:ratedTransitTimeEnquiry/r:cutOffTimeEnquiry/r:shippingDate", namespaces=ns) == "2026-11-09"
        assert root.findtext("r:ratedTransitTimeEnquiry/r:cutOffTimeEnquiry/r:packageLines/r:packageLine/r:numberOfPackages", namespaces=ns) == "1"
        return httpx.Response(200, text=QUOTES)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await probe_rtt(SETTINGS, client, DAY, case, NOW)
    assert len(calls) == 1 and result["query_state"] == "available" and result["environment"] == "uat"
    assert result["sample"].startswith("RYDE" if case == "invalid_route" else "GLADESVILLE")
    assert "fixture-password" not in str(result) and "12345678" not in str(result)


@pytest.mark.anyio
@pytest.mark.parametrize("code,body,state", [(200, AUTH_ERROR, "authentication_failed"), (200, RULE_ERROR, "invalid_request"), (200, '<html>private upstream</html>', "invalid_response"), (200, 'broken XML', "invalid_response"), (401, '', "authentication_failed"), (429, '', "rate_limited"), (500, '', "upstream_error"), (302, '', "upstream_error")])
async def test_http_200_does_not_mask_errors_and_redirect_never_followed(code, body, state):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(code, text=body, headers={"location": "https://untrusted.example"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await probe_rtt(SETTINGS, client, DAY, local_time=NOW)
    assert len(calls) == 1 and result["query_state"] == state
    assert "private upstream" not in str(result)


@pytest.mark.anyio
async def test_missing_config_or_invalid_inputs_do_not_send_request():
    def forbidden(request):
        pytest.fail("No request expected")
    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as client:
        assert (await probe_rtt(Settings(), client, DAY, local_time=NOW))["query_state"] == "not_configured"
        with pytest.raises(ValueError):
            await probe_rtt(SETTINGS, client, DAY, "unknown", NOW)
        with pytest.raises(ValueError):
            await probe_rtt(SETTINGS, client, DAY, local_time=datetime(2026, 11, 7))


@pytest.mark.anyio
@pytest.mark.parametrize("exception,state", [(httpx.ConnectError, "network_error"), (httpx.ReadTimeout, "timeout")])
async def test_network_failure_no_retry_or_credentials_in_error(exception, state):
    calls = []
    def handler(request):
        calls.append(request)
        raise exception("fixture-password", request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await probe_rtt(SETTINGS, client, DAY, local_time=NOW)
    assert len(calls) == 1 and result["query_state"] == state and "fixture-password" not in str(result)
