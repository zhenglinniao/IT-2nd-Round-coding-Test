import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    data_dir: Path = ROOT / "data"
    auspost_key: str = ""
    auspost_secret: str = ""
    startrack_account: str = ""
    post_account: str = ""
    auspost_base_url: str = "https://digitalapi.auspost.com.au/test/shipping/v1"
    shipping_enabled: bool = False
    tnt_enabled: bool = False

    def __post_init__(self):
        url = urlparse(self.auspost_base_url)
        if url.scheme != "https" or url.hostname != "digitalapi.auspost.com.au" or url.username or url.query or url.fragment:
            raise ValueError("AUSPOST_BASE_URL 必须使用澳大利亚邮政的官方 HTTPS 接口地址")
        if url.path.rstrip("/") not in ("/test/shipping/v1", "/shipping/v1"):
            raise ValueError("不支持此澳大利亚邮政接口路径")

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env")
        return cls(
            data_dir=Path(os.getenv("DATA_DIR") or ROOT / "data"),
            auspost_key=os.getenv("AUSPOST_API_KEY", ""),
            auspost_secret=os.getenv("AUSPOST_API_SECRET", ""),
            startrack_account=os.getenv("AUSPOST_STARTRACK_ACCOUNT", ""),
            post_account=os.getenv("AUSPOST_POST_ACCOUNT", ""),
            auspost_base_url=os.getenv("AUSPOST_BASE_URL") or cls.auspost_base_url,
            shipping_enabled=os.getenv("SHIPPING_ESTIMATE_ENABLED", "").lower() == "true",
            tnt_enabled=os.getenv("TNT_TRACKING_ENABLED", "true").lower() == "true",
        )
