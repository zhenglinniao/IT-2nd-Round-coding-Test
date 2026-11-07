"""Opt-in TNT diagnostics; portal compatibility and RTTNet API are distinct.

The two verified official login forms and the dedicated RTTNet UAT quote
endpoint can be contacted. No redirects are followed, no raw responses or
credentials are returned, and no booking/label operation is available.
"""
import argparse
import asyncio
import json
from datetime import date

import httpx

from backend.app.config import Settings
from backend.app.tnt import Page
from backend.app.tnt_rtt import probe_rtt

PORTALS = {
    "weblinking": "https://www.tntexpress.com.au/TNTOnline/Login.aspx",
    "uat": "https://uat.tntexpress.com.au/TNTOnline/Login.aspx",
}


def portal_form(response):
    response.raise_for_status()
    if response.status_code != 200 or len(response.content) > 2_000_000:
        raise ValueError("Unexpected portal response")
    page = Page(response.text)
    forms = page.root.find(lambda node: node.tag == "form" and node.attrs.get("id") == "form1")
    if len(forms) != 1 or forms[0].attrs.get("action") != "./Login.aspx" or forms[0].attrs.get("method", "").lower() != "post":
        raise ValueError("Changed login form")
    inputs = forms[0].find(lambda node: node.tag == "input" and "name" in node.attrs)
    names = {node.attrs["name"] for node in inputs}
    if not {"txtUserName", "txtPassword", "btn_login", "__VIEWSTATE", "antiforgeryLogin"}.issubset(names):
        raise ValueError("Missing login fields")
    fields = {node.attrs["name"]: node.attrs.get("value", "") for node in inputs if node.attrs.get("type") == "hidden"}
    if not fields["__VIEWSTATE"] or not fields["antiforgeryLogin"]:
        raise ValueError("Missing antiforgery state")
    return fields


async def diagnose_portal(service, settings, client):
    # Fixed endpoint mapping: callers cannot redirect credentials to arbitrary
    # hosts or use the domestic UAT credentials at the production login.
    url = PORTALS[service]
    if service == "weblinking":
        username, password = settings.tnt_weblinking_username, settings.tnt_weblinking_password
        complete = bool(username and password)
    else:
        username, password = settings.tnt_uat_username, settings.tnt_uat_password
        complete = bool(username and password and settings.tnt_uat_account)
    base = {"service": service, "credential_configured": complete,
            "probe": "TNT Online 门户兼容性核验，不是专用 Weblinking 或 RTT API 验证",
            "account_api_verified": False}
    if not complete:
        return {**base, "state": "not_configured", "message": "该组服务端凭据不完整，未发送请求。"}
    try:
        async with asyncio.timeout(35):
            first = await client.get(url, follow_redirects=False)
            fields = portal_form(first)
            fields.update(txtUserName=username, txtPassword=password, btn_login="Log in")
            response = await client.post(url, data=fields, follow_redirects=False)
            if response.status_code in (301, 302, 303, 307, 308):
                # A redirect alone proves neither authentication nor API access.
                return {**base, "state": "authentication_unconfirmed", "message": "门户返回跳转，未跟随；不能据此确认认证或账户 API 可用。"}
            response.raise_for_status()
            if response.status_code != 200 or len(response.content) > 2_000_000:
                raise ValueError("Unexpected login response")
            if "invalid user name or password" in response.text.lower():
                return {**base, "state": "portal_rejected", "message": "门户提示用户名或密码无效；不代表专用 Weblinking/RTT 凭据已失效，需匹配的正式协议。"}
            return {**base, "state": "authentication_unconfirmed", "message": "未获得可验证的认证成功证据；不能确认账户 API 可用。"}
    except (TimeoutError, httpx.TimeoutException):
        return {**base, "state": "timeout", "message": "TNT 官方门户核验超时，未重试。"}
    except httpx.RequestError:
        return {**base, "state": "network_error", "message": "无法连接 TNT 官方门户，未重试。"}
    except httpx.HTTPStatusError as error:
        code = error.response.status_code
        return {**base, "state": "rate_limited" if code == 429 else "endpoint_unavailable",
                "http_status": code, "message": "TNT 官方门户拒绝请求或暂不可用。"}
    except (ValueError, TypeError, RecursionError):
        return {**base, "state": "invalid_response", "message": "门户表单或响应格式不匹配，已停止核验。"}


async def run(service, shipping_date=None, rtt_controls=False):
    settings = Settings.from_env()
    if service == "rtt":
        cases = ["valid", "invalid_password", "invalid_route"] if rtt_controls else ["valid"]
        async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=10), follow_redirects=False) as client:
            for case in cases:
                result = await probe_rtt(settings, client, shipping_date, case)
                print(json.dumps(result, ensure_ascii=True))
        return
    for item in ([service] if service != "all" else list(PORTALS)):
        # Separate cookie jars for the two credential groups and hosts.
        async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=10), follow_redirects=False) as client:
            result = await diagnose_portal(item, settings, client)
            print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="手动 TNT 门户核验或专用 RTT UAT 样例报价验证；不创建运单")
    parser.add_argument("--service", choices=["weblinking", "uat", "all", "rtt"], default="all", help="all 仅包含两项门户探测；rtt 单独验证专用报价 API")
    parser.add_argument("--shipping-date", type=date.fromisoformat, help="RTT 样例寄件日期 YYYY-MM-DD，建议未来工作日")
    parser.add_argument("--rtt-controls", action="store_true", help="额外进行一次错误密码和一次无效地区的对照，只适用于 rtt")
    args = parser.parse_args()
    if args.service == "rtt" and args.shipping_date is None:
        parser.error("--service rtt 必须提供 --shipping-date")
    if args.rtt_controls and args.service != "rtt":
        parser.error("--rtt-controls 仅适用于 --service rtt")
    asyncio.run(run(args.service, args.shipping_date, args.rtt_controls))
