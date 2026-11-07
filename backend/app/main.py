import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .calculations import build_order
from .config import ROOT, Settings
from .repository import DataError, Repository
from .tracking import TrackingService


def create_app(settings: Settings | None = None, transport=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        app.state.repository = None
        app.state.data_error = None
        try:
            app.state.repository = Repository(settings.data_dir)
        except DataError as error:
            app.state.data_error = str(error)
        async with httpx.AsyncClient(timeout=httpx.Timeout(8, connect=5), follow_redirects=False, transport=transport) as client:
            app.state.tracking = TrackingService(settings, client)
            yield

    app = FastAPI(title="订单工作台 API", version="1.0.0", lifespan=lifespan)

    def repository():
        if app.state.data_error:
            raise HTTPException(503, detail=app.state.data_error)
        return app.state.repository

    def get_order(order_id):
        repo = repository()
        if order_id in repo.invalid_orders:
            raise HTTPException(422, detail={"message": "订单数据无效", "problems": repo.invalid_orders[order_id]["problems"]})
        if order_id not in repo.orders:
            raise HTTPException(404, detail="未找到订单。")
        return repo.orders[order_id]

    @app.get("/api/health", summary="检查服务与数据状态")
    def health():
        # Liveness is independent of files and remote carrier availability.
        return {"status": "ok", "data_ready": app.state.data_error is None}

    @app.get("/api/orders", summary="获取订单列表")
    def orders():
        repo = repository()
        result = []
        for order in repo.orders.values():
            detail = build_order(order, repo.products, repo.product_errors, settings.shipping_enabled)
            result.append({"id": order.id, "date": order.date.isoformat(), "status": order.status, "company": order.customer.company, "customer_name": order.customer.name, "item_count": len(order.items), "shipment_count": len(order.shipments), "complete": detail["complete"], "total": detail["totals"]["total"] if detail["totals"] else None, "problems": detail["problems"]})
        result.extend(repo.invalid_orders.values())
        return {"orders": result, "catalog_note": repo.catalog_note}

    @app.get("/api/orders/{order_id}", summary="获取订单详情")
    def order_detail(order_id: str):
        order = get_order(order_id)
        repo = repository()
        return {**build_order(order, repo.products, repo.product_errors, settings.shipping_enabled), "catalog_note": repo.catalog_note}

    @app.get("/api/orders/{order_id}/tracking", summary="查询订单物流")
    async def tracking(order_id: str):
        order = get_order(order_id)
        results = await asyncio.gather(*(app.state.tracking.track(shipment) for shipment in order.shipments))
        return {"order_id": order_id, "shipments": results, "cache_ttl_seconds": 60}

    dist = ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(dist / "index.html")

        @app.get("/{path:path}")
        def missing(path: str):
            # Unknown API routes must never be answered with the SPA HTML.
            return JSONResponse({"detail": "未找到资源。"}, status_code=404)
    return app


app = create_app()
