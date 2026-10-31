"""sddctx 运行配置:全部通过环境变量与默认相对路径解析,评审环境无需手改代码。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MINIMAX_BASE_URL_CN = "https://api.minimaxi.com/v1"
DEFAULT_MINIMAX_BASE_URL_INTL = "https://api.minimax.io/v1"
DEFAULT_MINIMAX_MODEL = "MiniMax-M3.1-Flash"
DEFAULT_POWERCONTEXT_URL = "http://127.0.0.1:8000"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


@dataclass(frozen=True)
class Settings:
    """sddctx 的全部可配置项。

    SDDCTX_HOME 默认取本包所在仓库的 minimax/ 目录,保证在任意 cwd 下
    都能找到规格、业务工程与记录目录。
    """

    home: Path
    seekdb_path: Path
    powercontext_url: str
    powercontext_token: str | None
    project_key: str
    minimax_api_key: str | None
    minimax_base_url: str
    minimax_model: str
    minimax_temperature: float
    minimax_max_tokens: int | None
    db_query_log: Path
    powercontext_log: Path

    @classmethod
    def load(cls) -> "Settings":
        home = Path(_env("SDDCTX_HOME", "") or Path(__file__).resolve().parents[2])
        home = home.resolve()
        data_dir = Path(_env("SDDCTX_DATA_DIR", "") or home / ".sddctx-data").resolve()
        records_dir = home / "records"
        records_dir.mkdir(parents=True, exist_ok=True)
        base_url = _env("SDDCTX_MINIMAX_BASE_URL", DEFAULT_MINIMAX_BASE_URL_CN)
        max_tokens_raw = _env("SDDCTX_MINIMAX_MAX_TOKENS")
        return cls(
            home=home,
            seekdb_path=Path(_env("SDDCTX_SEEKDB_PATH", "") or data_dir / "seekdb"),
            powercontext_url=_env("SDDCTX_POWERCONTEXT_URL", DEFAULT_POWERCONTEXT_URL),
            powercontext_token=_env("SDDCTX_POWERCONTEXT_TOKEN"),
            project_key=_env("SDDCTX_PROJECT_KEY", "minimax-sdd"),
            minimax_api_key=_env("SDDCTX_MINIMAX_API_KEY", os.environ.get("MINIMAX_API_KEY")),
            minimax_base_url=base_url,
            minimax_model=_env("SDDCTX_MINIMAX_MODEL", DEFAULT_MINIMAX_MODEL),
            minimax_temperature=float(_env("SDDCTX_MINIMAX_TEMPERATURE", "1.0")),
            minimax_max_tokens=int(max_tokens_raw) if max_tokens_raw else None,
            db_query_log=records_dir / "db-query-log.md",
            powercontext_log=records_dir / "powercontext-log.md",
        )

    @property
    def specs_dir(self) -> Path:
        return self.home / "specs"

    @property
    def sample_project_dir(self) -> Path:
        return self.home / "sample-project"

    @property
    def records_dir(self) -> Path:
        return self.home / "records"


def redact(value: str | None) -> str:
    """日志/记录中脱敏密钥。"""
    if not value:
        return "<unset>"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}(redacted)"
