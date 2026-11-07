from urllib.parse import parse_qs

import httpx
import pytest

from backend.app.config import Settings
from backend.tnt_diagnostics import PORTALS, diagnose_portal

SETTINGS = Settings(tnt_weblinking_username="private-user", tnt_weblinking_password="private-password",
                    tnt_uat_username="uat-user", tnt_uat_password="uat-password", tnt_uat_account="12345678")
FORM = '''<form id="form1" method="post" action="./Login.aspx">
<input type="hidden" name="__VIEWSTATE" value="fixture">
<input type="hidden" name="antiforgeryLogin" value="token">
<input name="txtUserName"><input name="txtPassword"><input name="btn_login"></form>'''


@pytest.mark.anyio
@pytest.mark.parametrize("service", ["weblinking", "uat"])
async def test_credentials_use_the_correct_host_post_body_and_antiforgery_token(service):
    calls = []
    def handler(request):
        calls.append(request)
        assert str(request.url) == PORTALS[service]
        assert "authorization" not in request.headers
        if request.method == "POST":
            fields = parse_qs(request.content.decode())
            assert fields["antiforgeryLogin"] == ["token"]
            expected = "private-user" if service == "weblinking" else "uat-user"
            assert fields["txtUserName"] == [expected]
            return httpx.Response(200, text="<script>jAlert('Invalid User name or Password','Error!');</script>")
        return httpx.Response(200, text=FORM)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await diagnose_portal(service, SETTINGS, client)
    assert len(calls) == 2 and result["state"] == "portal_rejected"
    assert not result["account_api_verified"]
    assert "private-user" not in str(result) and "private-password" not in str(result)


@pytest.mark.anyio
@pytest.mark.parametrize("status,body,state", [(302, "", "authentication_unconfirmed"), (200, "Welcome", "authentication_unconfirmed"), (429, "private upstream", "rate_limited"), (500, "private upstream", "endpoint_unavailable")])
async def test_redirect_or_http_200_never_claims_account_api_success(status, body, state):
    calls = []
    def handler(request):
        calls.append(request)
        if request.method == "GET":return httpx.Response(200, text=FORM)
        return httpx.Response(status, text=body, headers={"location": "https://untrusted.example"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await diagnose_portal("weblinking", SETTINGS, client)
    assert len(calls) == 2 and result["state"] == state
    assert not result["account_api_verified"] and "private upstream" not in str(result)


@pytest.mark.anyio
async def test_missing_config_or_changed_form_never_posts_credentials():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        return httpx.Response(200, text=FORM.replace('name="antiforgeryLogin"', 'name="changed"'))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (await diagnose_portal("uat", Settings(), client))["state"] == "not_configured"
        assert not calls
        assert (await diagnose_portal("uat", SETTINGS, client))["state"] == "invalid_response"
    assert len(calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("exception,state", [(httpx.ConnectError, "network_error"), (httpx.ReadTimeout, "timeout")])
async def test_network_errors_do_not_leak_or_retry(exception, state):
    calls = []
    def handler(request):
        calls.append(request)
        raise exception("private-password", request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await diagnose_portal("uat", SETTINGS, client)
    assert len(calls) == 1 and result["state"] == state and "private-password" not in str(result)


def test_settings_repr_omits_all_credentials():
    rendered = repr(SETTINGS)
    assert all(value not in rendered for value in ("private-user", "private-password", "uat-user", "uat-password", "12345678"))


def test_two_credential_groups_load_from_server_environment(monkeypatch):
    monkeypatch.setattr("backend.app.config.load_dotenv", lambda *_: None)
    expected = {
        "TNT_WEBLINKING_USERNAME": "private-user", "TNT_WEBLINKING_PASSWORD": "private-password",
        "TNT_UAT_USERNAME": "uat-user", "TNT_UAT_PASSWORD": "uat-password", "TNT_UAT_ACCOUNT": "12345678",
    }
    for key, value in expected.items():
        monkeypatch.setenv(key, value)
    settings = Settings.from_env()
    for key, value in expected.items():
        assert getattr(settings, key.lower()) == value
