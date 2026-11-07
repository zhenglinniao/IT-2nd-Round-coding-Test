import json
from pathlib import Path

from pydantic import ValidationError

from .models import Order, Product


class DataError(Exception):
    """A source file cannot be processed safely."""


def read_array(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise DataError(f"无法读取 {path.name}，请检查文件是否存在且为有效 JSON。") from None
    if not isinstance(data, list):
        raise DataError(f"{path.name} 顶层必须是数组。")
    return data


def unique_records(records, key, filename):
    result = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get(key), str) or not record[key].strip():
            raise DataError(f"{filename} 包含缺失或无效的 {key}。")
        value = record[key].strip()
        if value in result:
            raise DataError(f"{filename} 包含重复的 {key}: {value}。")
        result[value] = record
    return result


def validation_messages(error: ValidationError):
    # Avoid echoing arbitrary source input or credentials in error responses.
    messages = {
        "missing": "缺少必填字段", "extra_forbidden": "包含不支持的字段",
        "int_type": "必须是整数，不能使用小数、文本或布尔值",
        "int_parsing": "无法解析为整数", "greater_than": "必须大于规定的最小值",
        "greater_than_equal": "不得小于规定的最小值", "less_than_equal": "超过允许的最大值",
        "finite_number": "必须是有限数值", "decimal_max_places": "金额最多保留两位小数",
        "decimal_parsing": "必须是有效的十进制数值", "decimal_type": "数值类型无效",
        "string_type": "必须是文本", "string_too_short": "文本不能为空或长度不足",
        "string_too_long": "文本超过允许长度", "string_pattern_mismatch": "文本格式不符合要求",
        "literal_error": "不是允许的选项", "date_from_datetime_parsing": "日期必须为有效的 ISO 日期",
        "date_from_datetime_inexact": "请提供日期，不要包含时间",
        "date_type": "日期格式无效", "too_short": "记录数量不足",
        "list_type": "必须是数组", "model_type": "必须是结构正确的对象",
    }
    return [f"{'.'.join(str(v) for v in e['loc'])}：{messages.get(e['type'], '字段值不符合要求')}" for e in error.errors(include_input=False, include_url=False)]


class Repository:
    def __init__(self, data_dir: Path):
        raw_orders = unique_records(read_array(data_dir / "orders.json"), "id", "orders.json")
        raw_products = unique_records(read_array(data_dir / "products.json"), "sku", "products.json")
        self.orders: dict[str, Order] = {}
        self.invalid_orders: dict[str, dict] = {}
        self.products: dict[str, Product] = {}
        self.product_errors: dict[str, list[str]] = {}
        self.catalog_note = "商品价格来自本地商品数据文件。"
        metadata = data_dir / "catalog-source.json"
        if metadata.exists():
            try:
                self.catalog_note = str(json.loads(metadata.read_text(encoding="utf-8"))["note"])
            except (OSError, ValueError, KeyError, TypeError):
                raise DataError("catalog-source.json 格式无效。") from None
        for sku, raw in raw_products.items():
            try:
                self.products[sku] = Product.model_validate(raw)
            except ValidationError as error:
                self.product_errors[sku] = validation_messages(error)
        for order_id, raw in raw_orders.items():
            try:
                order = Order.model_validate(raw)
                self.validate_links(order)
                self.orders[order_id] = order
            except (ValidationError, DataError) as error:
                problems = validation_messages(error) if isinstance(error, ValidationError) else [str(error)]
                customer = raw.get("customer")
                self.invalid_orders[order_id] = {
                    "id": order_id, "date": None, "status": "数据无效",
                    "company": str(customer.get("company", "待修正订单")) if isinstance(customer, dict) else "待修正订单",
                    "customer_name": "—", "item_count": 0, "shipment_count": 0,
                    "complete": False, "total": None, "problems": problems,
                }

    @staticmethod
    def validate_links(order: Order):
        shipment_ids = [s.id for s in order.shipments]
        tracking_ids = [(s.carrier, s.tracking_number) for s in order.shipments]
        line_ids = [line.id for line in order.items]
        if len(shipment_ids) != len(set(shipment_ids)) or len(tracking_ids) != len(set(tracking_ids)):
            raise DataError("同一订单内包裹 ID 或承运商/运单号重复。")
        if len(line_ids) != len(set(line_ids)):
            raise DataError("订单明细 ID 重复。")
        referenced = {line.shipment_id for line in order.items}
        if referenced != set(shipment_ids):
            raise DataError("商品与包裹关联无效：存在未知引用或没有商品的包裹。")
