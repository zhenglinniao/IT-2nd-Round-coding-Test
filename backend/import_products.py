"""Normalize an exported assessment query JSON without guessing its units."""
import argparse
import json
import re
from decimal import Decimal
from pathlib import Path

from backend.app.models import Product


def measurement(value, factors):
    if value is None or value == "":
        return None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([^\d\s]+)\s*", str(value))
    if not match or match[2] not in factors:
        raise ValueError(f"Unknown measurement unit: {value!r}")
    return str(Decimal(match[1]) * factors[match[2]])


def normalize_rows(payload):
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("Input must be a rows array or a query response containing rows")
    products, seen = [], set()
    for row in rows:
        sku = str(row["SKU"]).strip()
        if sku in seen:
            raise ValueError(f"Duplicate SKU: {sku}")
        seen.add(sku)
        product = {
            "sku": sku, "name": row["ProductName"].strip(), "rrp": str(Decimal(str(row["RRP"]))),
            "weight_kg": measurement(row.get("weight"), {"g": Decimal("0.001"), "kg": Decimal(1)}),
            "volume_m3": measurement(row.get("volume"), {"mm³": Decimal("0.000000001"), "cm³": Decimal("0.000001"), "m³": Decimal(1)}),
        }
        for dimension in ("length", "width", "height"):
            product[dimension + "_cm"] = measurement(row.get(dimension), {"mm": Decimal("0.1"), "cm": Decimal(1), "m": Decimal(100)})
        products.append(Product.model_validate(product).model_dump(mode="json"))
    return products


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/products.json"))
    args = parser.parse_args()
    try:
        products = normalize_rows(json.loads(args.input.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Import failed: {error}\n")
    args.output.write_text(json.dumps(products, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Imported {len(products)} products into {args.output}")


if __name__ == "__main__":
    main()
