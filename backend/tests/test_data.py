import json

import pytest

from backend.app.models import Product
from backend.app.repository import DataError, Repository
from backend.import_products import measurement, normalize_rows


@pytest.mark.parametrize("quantity", [0, -2, 1.1, "3", True, None])
def test_bad_order_does_not_block_valid_order(data_dir, order_raw, quantity):
    bad = {**order_raw, "id": "BAD", "items": [{**order_raw["items"][0], "quantity": quantity}]}
    (data_dir / "orders.json").write_text(json.dumps([bad, order_raw]), encoding="utf-8")
    repo = Repository(data_dir)
    assert "BAD" in repo.invalid_orders
    assert order_raw["id"] in repo.orders


@pytest.mark.parametrize("kind", ["order_id", "product_sku", "shipment_id", "tracking_number", "line_id", "unknown_shipment"])
def test_duplicate_keys_and_invalid_relationships(data_dir, order_raw, kind):
    if kind in ("order_id", "product_sku"):
        name = "orders.json" if kind == "order_id" else "products.json"
        records = json.loads((data_dir / name).read_text())
        records.append(records[0])
        (data_dir / name).write_text(json.dumps(records))
        with pytest.raises(DataError):
            Repository(data_dir)
    else:
        if kind in ("shipment_id", "tracking_number"):
            copy = dict(order_raw["shipments"][0])
            if kind == "tracking_number":
                copy["id"] = "another"
            order_raw["shipments"].append(copy)
        elif kind == "line_id":
            order_raw["items"][1]["id"] = order_raw["items"][0]["id"]
        else:
            order_raw["items"][0]["shipment_id"] = "unknown"
        (data_dir / "orders.json").write_text(json.dumps([order_raw]))
        assert order_raw["id"] in Repository(data_dir).invalid_orders


@pytest.mark.parametrize("content", ["{broken", "{}", "null"])
def test_bad_file_reports_actionable_data_error(data_dir, content):
    (data_dir / "orders.json").write_text(content)
    with pytest.raises(DataError, match="orders.json"):
        Repository(data_dir)


@pytest.mark.parametrize("rrp", ["-1", "NaN", "Infinity", "0.001"])
def test_product_price_validation(rrp):
    with pytest.raises(ValueError):
        Product(sku="X", name="Fixture", rrp=rrp)


def test_empty_order_set_is_valid(data_dir):
    (data_dir / "orders.json").write_text("[]")
    assert not Repository(data_dir).orders


def test_import_converts_real_source_units_without_using_volumetric_gross_weight():
    products = normalize_rows({"rows": [{"SKU": "X", "ProductName": " Fixture ", "RRP": "99.00", "weight": "56.0g", "length": "67.0mm", "width": "67.0mm", "height": "104.0mm", "volume": "466856.0mm³", "Volumetric_GrossWeight": "0.1kg"}]})
    assert products[0]["weight_kg"] == "0.0560"
    assert products[0]["length_cm"] == "6.70"
    assert products[0]["volume_m3"] == "0.0004668560"


def test_import_rejects_unknown_units_and_duplicate_products():
    with pytest.raises(ValueError, match="unit"):
        measurement("123", {"kg": 1})
    row = {"SKU": "X", "ProductName": "Fixture", "RRP": "1"}
    with pytest.raises(ValueError, match="Duplicate"):
        normalize_rows([row, row])
