"""Read-only RTTNet UAT verification, separate from order shipping charges.

The sample requests a quote only: one 1 kg, 10 x 10 x 10 cm parcel, sender pays,
Gladesville NSW 2111 -> Fitzroy VIC 3065. It cannot book or create a shipment.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from urllib.parse import quote
from xml.etree import ElementTree as ET

import httpx

URL = "https://uat.tntexpress.com.au/rttnet/inputrequest.aspx"
NAMESPACE = "http://www.tntexpress.com.au"
TIMEOUT = httpx.Timeout(20, connect=10)


def normalize_rtt(text):
    # Do not resolve declarations or expand entities from an external service.
    if len(text) > 2_000_000 or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper() or "\x00" in text:
        raise ValueError("Unsafe or oversized XML")
    root = ET.fromstring(text)
    if root.tag not in ("response", f"{{{NAMESPACE}}}response"):
        raise ValueError("Unexpected RTT root")
    namespace = {"r": NAMESPACE} if root.tag.startswith("{") else {}
    prefix = "r:" if namespace else ""

    def path(*parts):
        return "/".join(prefix + part for part in parts)

    def codes(nodes):
        found = [node.findtext(path("code"), namespaces=namespace) for node in nodes]
        return [code for code in found if code and re.fullmatch(r"[A-Za-z0-9_-]{1,32}", code)]

    errors = root.findall(path("error"), namespace)
    if errors:
        values = codes(errors)
        return {"query_state": "authentication_failed" if "004" in values else "upstream_error", "error_codes": values,
                "message": "RTT 接口拒绝认证。" if "004" in values else "RTT 接口返回业务错误。"}
    response = root.find(path("ratedTransitTimeResponse"), namespace)
    if response is None:
        raise ValueError("Missing RTT response")
    rules = response.findall(path("brokenRules", "brokenRule"), namespace)
    if rules:
        return {"query_state": "invalid_request", "error_codes": codes(rules), "message": "RTT 业务校验未通过，请检查地区、邮编和包裹参数。"}
    products = response.findall(path("ratedProducts", "ratedProduct"), namespace)
    if not products:
        return {"query_state": "unavailable", "message": "RTT 未返回可报价服务。"}
    quotes = []
    for product in products:
        code = product.findtext(path("product", "code"), namespaces=namespace)
        cost = product.find(path("quote"), namespace)
        if not code or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", code) or cost is None or cost.get("currency") != "AUD":
            raise ValueError("Invalid RTT product")
        try:
            price = Decimal(cost.findtext(path("price"), namespaces=namespace) or "")
        except InvalidOperation as error:
            raise ValueError("Invalid RTT price") from error
        if not price.is_finite() or price < 0 or price > Decimal("1000000") or price.as_tuple().exponent < -2:
            raise ValueError("Invalid RTT price")
        # Do not echo raw upstream error descriptions, account data or HTML.
        quotes.append({"service_code": code, "currency": "AUD", "price": format(price, ".2f")})
    return {"query_state": "available", "quotes": quotes, "message": "RTT UAT 返回了样例包裹报价；不作为订单运费或生产报价。"}


def build_sample_xml(account, shipping_date, local_time, invalid_route=False):
    root = ET.Element("enquiry", xmlns=NAMESPACE)

    def node(parent, name, value=None, **attrs):
        result = ET.SubElement(parent, name, attrs)
        if value is not None:
            result.text = str(value)
        return result

    rated = node(root, "ratedTransitTimeEnquiry")
    cutoff = node(rated, "cutOffTimeEnquiry")
    for tag, suburb, postcode, state in (
        ("collectionAddress", "RYDE" if invalid_route else "GLADESVILLE", "2111", "NSW"),
        ("deliveryAddress", "FITZROY", "3065", "VIC"),
    ):
        address = node(cutoff, tag)
        for name, value in (("suburb", suburb), ("postCode", postcode), ("state", state)):
            node(address, name, value)
    node(cutoff, "shippingDate", shipping_date.isoformat())
    node(cutoff, "userCurrentLocalDateTime", local_time.isoformat(timespec="seconds"))
    node(node(cutoff, "dangerousGoods"), "dangerous", "false")
    line = node(node(cutoff, "packageLines", packageType="N"), "packageLine")
    node(line, "numberOfPackages", "1")
    dimensions = node(line, "dimensions", unit="cm")
    for name in ("length", "width", "height"):
        node(dimensions, name, "10")
    node(node(line, "weight", unit="kg"), "weight", "1")
    terms = node(rated, "termsOfPayment")
    node(terms, "senderAccount", account)
    node(terms, "payer", "S")
    return ET.tostring(root, encoding="unicode")


async def probe_rtt(settings, client, shipping_date: date, case="valid", local_time=None):
    if case not in ("valid", "invalid_password", "invalid_route"):
        raise ValueError("Unknown RTT verification case")
    now = local_time or datetime.now().astimezone()
    if not isinstance(shipping_date, date) or isinstance(shipping_date, datetime) or now.tzinfo is None:
        raise ValueError("Explicit shipping date and aware local time required")
    origin = "RYDE" if case == "invalid_route" else "GLADESVILLE"
    base = {"service": "rtt", "environment": "uat", "case": case, "shipping_date": shipping_date.isoformat(),
            "sample": f"{origin} NSW 2111 → FITZROY VIC 3065；1 件，1 kg，10×10×10 cm；仅测试报价"}
    if not all((settings.tnt_uat_username, settings.tnt_uat_password, settings.tnt_uat_account)):
        return {**base, "query_state": "not_configured", "message": "国内 UAT 凭据不完整，未发送报价请求。"}
    xml = build_sample_xml(settings.tnt_uat_account, shipping_date, now, invalid_route=case == "invalid_route")
    # RTTNet Version 2 consumes an encoded XMLRequest inside an encoded form.
    fields = {"Username": settings.tnt_uat_username,
              "Password": "__intentional_invalid_control__" if case == "invalid_password" else settings.tnt_uat_password,
              "Version": "2", "XMLRequest": quote(xml, safe="")}
    try:
        response = await client.post(URL, data=fields, headers={"Accept": "application/xml,text/xml"}, follow_redirects=False, timeout=TIMEOUT)
        if response.status_code in (401, 403):
            return {**base, "query_state": "authentication_failed", "http_status": response.status_code, "message": "RTT 接口拒绝授权。"}
        if response.status_code == 429:
            return {**base, "query_state": "rate_limited", "http_status": 429, "message": "RTT 查询频率受限。"}
        response.raise_for_status()
        if response.status_code != 200 or len(response.content) > 2_000_000:
            raise ValueError("Unexpected RTT response")
        return {**base, "http_status": 200, **normalize_rtt(response.text)}
    except httpx.TimeoutException:
        return {**base, "query_state": "timeout", "message": "RTT 查询超时，未重试。"}
    except httpx.RequestError:
        return {**base, "query_state": "network_error", "message": "无法连接 RTT 测试服务，未重试。"}
    except httpx.HTTPStatusError as error:
        return {**base, "query_state": "upstream_error", "http_status": error.response.status_code, "message": "RTT 接口暂不可用或拒绝跳转。"}
    except (ValueError, TypeError, RecursionError, ET.ParseError):
        return {**base, "query_state": "invalid_response", "message": "RTT 未返回有效的 XML 报价响应。"}
