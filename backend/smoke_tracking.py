"""Read-only carrier check. Reports normalized results, never auth or raw bodies."""
import asyncio
import json

import httpx

from backend.app.config import Settings
from backend.app.repository import Repository
from backend.app.tracking import TrackingService


async def main():
    settings = Settings.from_env()
    repo = Repository(settings.data_dir)
    async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
        service = TrackingService(settings, client)
        for order in repo.orders.values():
            for shipment in order.shipments:
                result = await service.track(shipment)
                print(json.dumps({k: result[k] for k in ("tracking_number", "query_state", "status", "last_update", "fetched_at", "message", "environment")}, ensure_ascii=True))


if __name__ == "__main__":
    asyncio.run(main())
