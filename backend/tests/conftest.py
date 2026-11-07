import json
from copy import deepcopy
from pathlib import Path

import pytest

from backend.app.config import ROOT


@pytest.fixture
def order_raw():
    return deepcopy(json.loads((ROOT / "data/orders.json").read_text(encoding="utf-8"))[0])


@pytest.fixture
def data_dir(tmp_path: Path, order_raw):
    (tmp_path / "orders.json").write_text(json.dumps([order_raw]), encoding="utf-8")
    (tmp_path / "products.json").write_text((ROOT / "data/products.json").read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


@pytest.fixture
def anyio_backend():
    return "asyncio"
