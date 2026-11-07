from decimal import Decimal

import pytest

from backend.app.calculations import build_order, estimate_shipping, price_line
from backend.app.config import ROOT
from backend.app.models import Order, Product
from backend.app.repository import Repository


@pytest.mark.parametrize("rrp,quantity,unit,subtotal", [
    ("22.00", 2, "20.00", "40.00"),
    ("199.00", 3, "180.91", "542.73"),
    ("0.00", 9, "0.00", "0.00"),
    ("0.05", 1, "0.05", "0.05"),
    ("0.11", 5, "0.10", "0.50"),
])
def test_price_line_has_fixed_decimal_expected_results(rrp, quantity, unit, subtotal):
    result = price_line(Decimal(rrp), quantity)
    assert result["unit_ex_gst"] == unit
    assert result["subtotal_ex_gst"] == subtotal


@pytest.mark.parametrize("quantity", [0, -1, 1.5, "2", True, None])
def test_invalid_quantity_never_coerced(quantity):
    with pytest.raises(ValueError):
        price_line(Decimal("22"), quantity)


@pytest.mark.parametrize("price", ["NaN", "Infinity", "-1"])
def test_invalid_price_rejected(price):
    with pytest.raises(ValueError):
        price_line(Decimal(price), 1)


def test_supplied_orders_have_independent_correct_totals_and_explicit_rounding():
    repo = Repository(ROOT / "data")
    results = [build_order(o, repo.products, repo.product_errors) for o in repo.orders.values()]
    assert results[0]["totals"] == {"subtotal_ex_gst": "1937.27", "rounding_adjustment": "-0.01", "gst": "193.73", "shipping": "0.00", "total": "2131.00"}
    assert results[1]["totals"] == {"subtotal_ex_gst": "1504.55", "rounding_adjustment": "0.00", "gst": "150.45", "shipping": "0.00", "total": "1655.00"}
    assert [len(r["items"]) for r in results] == [5, 4]
    for result in results:
        totals = result["totals"]
        assert sum(Decimal(i["subtotal_ex_gst"]) for i in result["items"]) + Decimal(totals["rounding_adjustment"]) == Decimal(totals["subtotal_ex_gst"])


def test_missing_sku_withholds_totals_but_preserves_other_lines(order_raw):
    repo = Repository(ROOT / "data")
    repo.products.pop("TBAMET10")
    detail = build_order(Order.model_validate(order_raw), repo.products, {})
    assert not detail["complete"] and detail["totals"] is None
    assert len(detail["items"]) == 5
    assert detail["items"][0]["rrp"] is None
    assert detail["items"][1]["matched"]


def test_formula_uses_quantity_volume_and_groups_once_per_package(order_raw):
    order_raw["items"] = [
        {"id": "a", "sku": "NEW", "quantity": 2, "shipment_id": "track-1"},
        {"id": "b", "sku": "NEW", "quantity": 1, "shipment_id": "track-1"},
    ]
    products = {"NEW": Product(sku="NEW", name="Synthetic fixture", rrp="22", weight_kg="0.2", width_cm="20", length_cm="20", height_cm="20")}
    result = estimate_shipping(Order.model_validate(order_raw), products, True)
    # 3 * .008 m3 * 250 = 6 chargeable kg. NSW -> VIC.
    assert result["amount"] == "22.00"
    assert len(result["packages"]) == 1
    assert result["packages"][0]["chargeable_kg"] == "6"
    order_raw["customer"]["address"]["state"] = "NSW"
    assert estimate_shipping(Order.model_validate(order_raw), products, True)["amount"] == "17.00"


def test_shipping_missing_dimensions_and_tnt_fall_back(order_raw):
    order_raw["items"] = [{"id": "a", "sku": "NEW", "quantity": 1, "shipment_id": "track-1"}]
    products = {"NEW": Product(sku="NEW", name="Synthetic fixture", rrp="22", weight_kg="1")}
    result = estimate_shipping(Order.model_validate(order_raw), products, True)
    assert result["amount"] == "0.00" and not result["complete"]
    assert result["packages"][0]["method"] == "unavailable"
    order_raw["shipments"][0]["carrier"] = "tnt"
    assert estimate_shipping(Order.model_validate(order_raw), products, True)["packages"][0]["method"] == "not_implemented"
