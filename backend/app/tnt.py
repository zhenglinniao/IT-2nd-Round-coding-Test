"""Read-only adapter for TNT Australia's public ASP.NET tracking pages.

No Weblinking credentials or shipment/label operations are used. Page structure
is validated; an upstream redesign fails explicitly rather than inventing status.
"""
import re
from datetime import datetime
from html.parser import HTMLParser

import httpx

ORIGIN = "https://www.tntexpress.com.au"
ENTRY = ORIGIN + "/interaction/trackntrace.aspx?navigation=1&respCountry=au&respLang=en"
PATHS = {"/interaction/trackntraceResult.aspx", "/interaction/ConsignmentHistory.aspx"}
TIMEOUT = httpx.Timeout(15, connect=10)


class Node:
    def __init__(self, tag="", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def text(self):
        return " ".join(" ".join(c.text() if isinstance(c, Node) else c for c in self.children).split())

    def find(self, predicate):
        return [self] * bool(predicate(self)) + [n for c in self.children if isinstance(c, Node) for n in c.find(predicate)]


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {"input", "img", "br", "hr", "meta", "link", "wbr", "source", "area", "base", "embed", "param", "col"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)

    def fields(self):
        fields = {n.attrs["name"]: n.attrs.get("value", "") for n in self.root.find(lambda n: n.tag == "input" and n.attrs.get("type") == "hidden" and "name" in n.attrs)}
        if not fields.get("__VIEWSTATE") or not fields.get("__EVENTVALIDATION"):
            raise ValueError("Unrecognized TNT form")
        return fields


def normalize_history(html, number):
    page = Page(html)
    sections = page.root.find(lambda n: n.attrs.get("id") == "bodycontent_divcollection")
    if len(sections) != 1:
        raise ValueError("Missing TNT history section")
    section = sections[0]
    if not re.search(r"Consignment:\s*" + re.escape(number) + r"\b", section.text()):
        raise ValueError("Mismatched TNT consignment")
    tables = section.find(lambda n: n.tag == "table")
    if len(tables) != 1:
        raise ValueError("Missing TNT history table")
    rows = tables[0].find(lambda n: n.tag == "tr")
    if not rows or [n.text() for n in rows[0].find(lambda n: n.tag in {"th", "td"})] != ["Status", "Date & Time", "Depot"]:
        raise ValueError("Changed TNT history columns")
    events = []
    for row in rows[1:]:
        cells = [n.text() for n in row.find(lambda n: n.tag == "td")]
        if len(cells) != 3 or not cells[0]:
            raise ValueError("Invalid TNT history row")
        # The public site supplies local-looking text without an offset. Keep it
        # as text; never manufacture a timezone or UTC timestamp.
        order = datetime.strptime(cells[1], "%d/%m/%Y %H:%M")
        events.append((order, {"description": cells[0], "location": cells[2] or None, "date": None, "date_text": cells[1]}))
    if not events:
        return {"query_state": "unavailable", "message": "TNT 官方暂未提供此运单的历史轨迹。"}
    events.sort(key=lambda pair: pair[0], reverse=True)
    unique = list({tuple(event.values()): event for _, event in events}.values())
    return {"query_state": "available", "status": unique[0]["description"], "last_update": None,
            "last_update_text": unique[0]["date_text"], "events": unique,
            "message": "来自 TNT 澳大利亚官方公开查询；官网时间未标注时区。"}


def checked(response):
    response.raise_for_status()
    if response.status_code != 200 or len(response.content) > 2_000_000:
        raise ValueError("Unexpected TNT response")
    return response.text


async def follow_result(client, response, expected_path):
    if response.status_code != 302:
        checked(response)
        raise ValueError("Missing TNT result redirect")
    url = response.url.join(response.headers.get("location", ""))
    if url.scheme != "https" or url.host != "www.tntexpress.com.au" or url.port not in (None, 443) or url.userinfo or url.path not in PATHS or url.path != expected_path:
        raise ValueError("Unexpected TNT redirect")
    result = await client.get(url, follow_redirects=False, timeout=TIMEOUT)
    checked(result)
    return result


async def query_tnt(client, number):
    if not re.fullmatch(r"\d{9}", number):
        return {"query_state": "unsupported_number", "message": "当前 TNT 国内追踪入口仅支持 9 位数字运单号。"}
    page = Page(checked(await client.get(ENTRY, follow_redirects=False, timeout=TIMEOUT)))
    fields = page.fields()
    fields.update({"__EVENTTARGET": "ctl00$bodycontent$btnSubmit", "__EVENTARGUMENT": "", "method": "CON", "TextArea": number})
    result = await follow_result(client, await client.post(ENTRY, data=fields, follow_redirects=False, timeout=TIMEOUT), "/interaction/trackntraceResult.aspx")
    page = Page(result.text)
    details = page.root.find(lambda n: n.attrs.get("id") == "bodycontent_A1" and n.tag == "a")
    if not details:
        errors = page.root.find(lambda n: n.attrs.get("id") == "bodycontent_lblErrorMessage")
        if errors and any(phrase in errors[0].text().lower() for phrase in ("not found", "no consignment", "unable to find")):
            return {"query_state": "not_found", "message": "TNT 官方未找到此运单，请核对运单号。"}
        raise ValueError("Missing TNT details link")
    fields = page.fields()
    fields.update({"__EVENTTARGET": "ctl00$bodycontent$A1", "__EVENTARGUMENT": ""})
    history = await follow_result(client, await client.post(result.url, data=fields, follow_redirects=False, timeout=TIMEOUT), "/interaction/ConsignmentHistory.aspx")
    return normalize_history(history.text, number)
