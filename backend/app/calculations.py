from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP, localcontext

from .models import Order, Product

CENT = Decimal("0.01")
TAX = Decimal("0.10")


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def price_line(rrp: Decimal, quantity: int) -> dict:
    if not rrp.is_finite() or rrp < 0 or type(quantity) is not int or quantity <= 0:
        raise ValueError("建议零售价必须为有限的非负金额，数量必须为正整数")
    with localcontext() as ctx:
        ctx.prec = 40
        unit = rrp / (1 + TAX)
        return {"rrp": money(rrp), "unit_ex_gst": money(unit), "subtotal_ex_gst": money(unit * quantity)}


def estimate_shipping(order: Order, products: dict[str, Product], enabled: bool) -> dict:
    packages = []
    for shipment in order.shipments:
        result = {"shipment_id": shipment.id, "amount": "0.00", "method": "not_estimated", "note": "尚未估算运费，按题目允许的方式暂显示 A$0.00。"}
        if shipment.carrier == "tnt":
            result.update(method="not_implemented", note="TNT 运费暂未接入，此包裹暂按 A$0.00 处理。")
        elif enabled:
            weight, volume = Decimal(0), Decimal(0)
            for line in (item for item in order.items if item.shipment_id == shipment.id):
                product = products.get(line.sku)
                if not product or product.weight_kg is None:
                    result.update(method="unavailable", note="缺少商品或商品重量，无法估算此包裹的运费。")
                    break
                dimensions = (product.width_cm, product.length_cm, product.height_cm)
                if product.volume_m3 is not None:
                    item_volume = product.volume_m3
                elif all(value is not None for value in dimensions):
                    item_volume = dimensions[0] * dimensions[1] * dimensions[2] / Decimal(1000000)
                else:
                    result.update(method="unavailable", note="缺少商品体积或完整尺寸，无法估算此包裹的运费。")
                    break
                weight += product.weight_kg * line.quantity
                volume += item_volume * line.quantity
            else:
                chargeable = max(weight, volume * Decimal(250)).to_integral_value(rounding=ROUND_CEILING)
                # Assessment-only formula, not a carrier quote. Origin 2111; same-state vs interstate.
                interstate = order.customer.address.state != "NSW"
                fee = Decimal(8) + chargeable * Decimal("1.50") + (Decimal(5) if interstate else Decimal(0))
                result.update(amount=money(fee), method="formula", note="示例估算：A$8 + 向上取整的计费公斤数 × A$1.50 + 跨州附加费 A$5；并非快递公司的报价。", weight_kg=str(weight), volume_m3=str(volume), chargeable_kg=str(chargeable))
        packages.append(result)
    return {
        "amount": money(sum((Decimal(p["amount"]) for p in packages), Decimal(0))),
        "method": "formula" if any(p["method"] == "formula" for p in packages) else "fallback",
        "complete": all(p["method"] == "formula" for p in packages),
        "packages": packages,
        "origin_postcode": "2111", "destination_postcode": order.customer.address.postcode,
    }


def build_order(order: Order, products: dict[str, Product], product_errors: dict, shipping_enabled=False):
    lines, problems = [], []
    for line in order.items:
        product = products.get(line.sku)
        item = line.model_dump()
        if product is None:
            reason = "商品数据无效" if line.sku in product_errors else "未找到 SKU 商品数据"
            problems.append(f"{line.sku}: {reason}")
            item.update(name=None, matched=False, rrp=None, unit_ex_gst=None, subtotal_ex_gst=None, problem=reason)
        else:
            item.update(name=product.name, matched=True, **price_line(product.rrp, line.quantity))
        lines.append(item)
    shipping = estimate_shipping(order, products, shipping_enabled)
    totals = None
    if not problems:
        with localcontext() as ctx:
            ctx.prec = 40
            precise_subtotal = sum((products[line.sku].rrp * line.quantity / (1 + TAX) for line in order.items), Decimal(0))
            subtotal = Decimal(money(precise_subtotal))
            gst = Decimal(money(precise_subtotal * TAX))
        displayed_sum = sum((Decimal(line["subtotal_ex_gst"]) for line in lines), Decimal(0))
        totals = {"subtotal_ex_gst": money(subtotal), "rounding_adjustment": money(subtotal - displayed_sum), "gst": money(gst), "shipping": shipping["amount"], "total": money(subtotal + gst + Decimal(shipping["amount"]))}
    return {
        **order.model_dump(mode="json", exclude={"items"}),
        "items": lines, "complete": not problems, "problems": problems,
        "totals": totals, "shipping": shipping, "currency": "AUD", "gst_rate": "0.10",
    }
