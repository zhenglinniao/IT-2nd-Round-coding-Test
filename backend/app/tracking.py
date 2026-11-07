import asyncio
from collections import deque
from datetime import datetime, timezone
from time import monotonic

import httpx

from .config import Settings
from .models import Shipment
from .tnt import query_tnt


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # A missing timezone is not silently assigned a location/timezone.
        return parsed if parsed.tzinfo else None
    except ValueError:
        return None


def normalize_auspost(payload, tracking_number):
    """Handle AP articles, legacy ST events and nested current AP items."""
    if not isinstance(payload, dict) or not isinstance(payload.get("tracking_results"), list):
        return {"query_state": "invalid_response", "message": "快递服务返回了无法识别的数据。"}
    result = next((r for r in payload["tracking_results"] if isinstance(r, dict) and r.get("tracking_id") == tracking_number), None)
    if result is None:
        return {"query_state": "not_found", "message": "返回结果中未找到对应运单号。"}
    if result.get("errors"):
        errors = result["errors"]
        not_found = isinstance(errors, list) and any(isinstance(e, dict) and str(e.get("code")) in ("ESB-10001", "ESB-10002", "51104") for e in errors)
        return {"query_state": "not_found" if not_found else "upstream_error", "message": "快递服务暂时无法提供此包裹的物流信息。"}
    events, statuses = [], []

    def visit(node):
        if not isinstance(node, dict):
            return
        if isinstance(node.get("status"), str) and node["status"].strip():
            statuses.append(node["status"])
        node_events = node.get("events", [])
        if not isinstance(node_events, list):
            raise ValueError("Invalid events")
        for event in node_events:
            if not isinstance(event, dict):
                raise ValueError("Invalid event")
            # Missing fields stay missing; fetched_at is never an event timestamp.
            description = event.get("description")
            if description is not None and not isinstance(description, str):
                raise ValueError("Invalid event description")
            if description or event.get("date"):
                events.append({"description": description or "物流事件", "location": event.get("location") if isinstance(event.get("location"), str) else None, "date": event.get("date") if timestamp(event.get("date")) else None})
        if "consignment" in node:
            visit(node["consignment"])
        for key in ("trackable_items", "items"):
            children = node.get(key, [])
            if not isinstance(children, list):
                raise ValueError("Invalid items")
            for child in children:
                if not isinstance(child, dict):
                    raise ValueError("Invalid item")
                visit(child)

    try:
        visit(result)
    except (ValueError, TypeError, RecursionError):
        return {"query_state": "invalid_response", "message": "快递服务返回的物流字段格式无效。"}
    deduplicated = {tuple(e.values()): e for e in events}
    events = sorted(deduplicated.values(), key=lambda e: timestamp(e["date"]) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    if not events and not statuses:
        return {"query_state": "unavailable", "message": "此包裹暂时没有可用的物流信息。"}
    consignment = result.get("consignment")
    preferred_status = result.get("status") or (consignment.get("status") if isinstance(consignment, dict) else None)
    if not isinstance(preferred_status, str) or not preferred_status.strip():
        # Without a consignment-level status, don't present the first delivered
        # article as if every article in the consignment had been delivered.
        preferred_status = " / ".join(dict.fromkeys(statuses)) or None
    return {
        "query_state": "available", "status": preferred_status,
        "last_update": next((e["date"] for e in events if e["date"]), None), "events": events,
        "message": "物流信息来自快递服务的实际响应。",
    }


class TrackingService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings, self.client = settings, client
        self.cache = {}
        self.lock = asyncio.Lock()
        self.requests = deque()

    async def track(self, shipment: Shipment):
        base = {**shipment.model_dump(), "status": None, "last_update": None, "events": [], "fetched_at": None, "cached": False, "environment": "testbed" if "/test/" in self.settings.auspost_base_url else "production"}
        if shipment.carrier == "tnt":
            return await self.track_tnt(shipment, {**base, "environment": "tnt_public"})
        account = self.settings.startrack_account if shipment.carrier == "startrack" else self.settings.post_account
        if not all((self.settings.auspost_key, self.settings.auspost_secret, account)):
            return {**base, "query_state": "not_configured", "message": "服务端尚未配置完整的快递查询凭据。"}
        key = (shipment.carrier, shipment.tracking_number, account)
        # Serialize small testbed requests, merge concurrent refreshes, cap at 10/min.
        async with self.lock:
            now = monotonic()
            cached = self.cache.get(key)
            if cached and now - cached[0] < 60:
                return {**base, **cached[1], "cached": True}
            while self.requests and now - self.requests[0] >= 60:
                self.requests.popleft()
            if len(self.requests) >= 10:
                return {**base, "query_state": "rate_limited", "message": "已达到每分钟 10 次的本地查询限制，请稍后重试。"}
            self.requests.append(now)
            try:
                response = await self.client.get(
                    f"{self.settings.auspost_base_url.rstrip('/')}/track",
                    params={"tracking_ids": shipment.tracking_number},
                    auth=httpx.BasicAuth(self.settings.auspost_key, self.settings.auspost_secret),
                    headers={"Account-Number": account, "Accept": "application/json"},
                )
                if response.status_code in (401, 403):
                    result = {"query_state": "authentication_failed", "message": f"快递接口拒绝授权（HTTP {response.status_code}），请检查账号权限。"}
                elif response.status_code == 429:
                    result = {"query_state": "rate_limited", "message": "快递接口查询频率受限，请稍后重试。"}
                elif response.status_code >= 400:
                    result = {"query_state": "upstream_error", "message": f"快递服务暂时不可用（HTTP {response.status_code}）。"}
                elif response.status_code != 200 or len(response.content) > 2_000_000:
                    result = {"query_state": "invalid_response", "message": "快递接口返回了异常响应。"}
                else:
                    result = normalize_auspost(response.json(), shipment.tracking_number)
            except httpx.TimeoutException:
                result = {"query_state": "timeout", "message": "快递查询超时，请稍后重试。"}
            except httpx.RequestError:
                result = {"query_state": "network_error", "message": "无法连接快递服务，请检查网络后重试。"}
            except (ValueError, TypeError):
                result = {"query_state": "invalid_response", "message": "快递接口未返回有效的 JSON 数据。"}
            result["fetched_at"] = datetime.now(timezone.utc).isoformat()
            self.cache[key] = (monotonic(), result)
            return {**base, **result}

    async def track_tnt(self, shipment, base):
        if not self.settings.tnt_enabled:
            return {**base, "query_state": "not_configured", "message": "服务端未启用 TNT 官方公开追踪查询。"}
        key = ("tnt", shipment.tracking_number)
        async with self.lock:
            now = monotonic()
            cached = self.cache.get(key)
            if cached and now - cached[0] < 60:
                return {**base, **cached[1], "cached": True}
            while self.requests and now - self.requests[0] >= 60:
                self.requests.popleft()
            if len(self.requests) >= 10:
                return {**base, "query_state": "rate_limited", "message": "已达到每分钟 10 次的本地查询限制，请稍后重试。"}
            self.requests.append(now)
            try:
                async with asyncio.timeout(30):
                    result = await query_tnt(self.client, shipment.tracking_number)
            except (TimeoutError, httpx.TimeoutException):
                result = {"query_state": "timeout", "message": "TNT 查询超时，请稍后重试。"}
            except httpx.HTTPStatusError as error:
                code = error.response.status_code
                state = "rate_limited" if code == 429 else "authentication_failed" if code in (401, 403) else "upstream_error"
                result = {"query_state": state, "message": f"TNT 官方查询暂时不可用（HTTP {code}）。"}
            except httpx.RequestError:
                result = {"query_state": "network_error", "message": "无法连接 TNT 官方查询服务，请稍后重试。"}
            except (ValueError, TypeError, RecursionError):
                result = {"query_state": "invalid_response", "message": "TNT 官方页面格式发生变化或返回结果不匹配，暂时无法读取轨迹。"}
            result["fetched_at"] = datetime.now(timezone.utc).isoformat()
            self.cache[key] = (monotonic(), result)
            return {**base, **result}
